"""HTML markdown visitor - renders AST nodes to HTML for the chat log."""

from __future__ import annotations

import re
from html import escape as html_escape
from io import StringIO
from typing import TYPE_CHECKING

from discord_chat_exporter.core.markdown.nodes import (
    EmojiNode,
    FormattingKind,
    FormattingNode,
    HeadingNode,
    InlineCodeBlockNode,
    LinkNode,
    ListItemNode,
    ListNode,
    MarkdownNode,
    MentionKind,
    MentionNode,
    MultiLineCodeBlockNode,
    TextNode,
    TimestampNode,
)
from discord_chat_exporter.core.markdown.parser import parse
from discord_chat_exporter.core.markdown.visitor import MarkdownVisitor

if TYPE_CHECKING:
    from discord_chat_exporter.core.exporting.context import ExportContext


def _html_encode(text: str) -> str:
    return html_escape(text, quote=True)


class HtmlMarkdownVisitor(MarkdownVisitor):
    """Renders a markdown AST to HTML suitable for the chatlog template."""

    def __init__(
        self,
        context: ExportContext,
        buffer: StringIO,
        is_jumbo: bool,
    ) -> None:
        self._context = context
        self._buffer = buffer
        self._is_jumbo = is_jumbo

    # -- text --

    async def visit_text(self, node: TextNode) -> None:
        self._buffer.write(_html_encode(node.text))

    # -- formatting --

    async def visit_formatting(self, node: FormattingNode) -> None:
        if node.kind == FormattingKind.BOLD:
            opening, closing = "<strong>", "</strong>"
        elif node.kind == FormattingKind.ITALIC:
            opening, closing = "<em>", "</em>"
        elif node.kind == FormattingKind.UNDERLINE:
            opening, closing = "<u>", "</u>"
        elif node.kind == FormattingKind.STRIKETHROUGH:
            opening, closing = "<s>", "</s>"
        elif node.kind == FormattingKind.SPOILER:
            opening = (
                '<span class="chatlog__markdown-spoiler chatlog__markdown-spoiler--hidden"'
                ' onclick="showSpoiler(event, this)">'
            )
            closing = "</span>"
        elif node.kind == FormattingKind.QUOTE:
            opening = (
                '<div class="chatlog__markdown-quote">'
                '<div class="chatlog__markdown-quote-border"></div>'
                '<div class="chatlog__markdown-quote-content">'
            )
            closing = "</div></div>"
        else:
            raise ValueError(f"Unknown formatting kind: {node.kind!r}")

        self._buffer.write(opening)
        await self.visit_many(node.children)
        self._buffer.write(closing)

    # -- heading --

    async def visit_heading(self, node: HeadingNode) -> None:
        self._buffer.write(f"<h{node.level}>")
        await self.visit_many(node.children)
        self._buffer.write(f"</h{node.level}>")

    # -- list --

    async def visit_list(self, node: ListNode) -> None:
        self._buffer.write("<ul>")
        await self.visit_many(node.items)
        self._buffer.write("</ul>")

    async def visit_list_item(self, node: ListItemNode) -> None:
        self._buffer.write("<li>")
        await self.visit_many(node.children)
        self._buffer.write("</li>")

    # -- code blocks --

    async def visit_inline_code_block(self, node: InlineCodeBlockNode) -> None:
        self._buffer.write(
            f'<code class="chatlog__markdown-pre chatlog__markdown-pre--inline">'
            f"{_html_encode(node.code)}</code>"
        )

    async def visit_multi_line_code_block(self, node: MultiLineCodeBlockNode) -> None:
        highlight_class = (
            f"language-{node.language}" if node.language.strip() else "nohighlight"
        )
        self._buffer.write(
            f'<code class="chatlog__markdown-pre chatlog__markdown-pre--multiline {highlight_class}">'
            f"{_html_encode(node.code)}</code>"
        )

    # -- links --

    async def visit_link(self, node: LinkNode) -> None:
        # Try to extract message ID if the link points to a Discord message
        msg_match = re.match(
            r"^https?://(?:discord|discordapp)\.com/channels/.*?/(\d+)/?$",
            node.url,
        )
        linked_message_id = msg_match.group(1) if msg_match else None

        if linked_message_id:
            self._buffer.write(
                f'<a href="{_html_encode(node.url)}" '
                f"""onclick="scrollToMessage(event, '{linked_message_id}')">"""
            )
        else:
            self._buffer.write(f'<a href="{_html_encode(node.url)}">')

        await self.visit_many(node.children)
        self._buffer.write("</a>")

    # -- emoji --

    async def visit_emoji(self, node: EmojiNode) -> None:
        jumbo_class = "chatlog__emoji--large" if self._is_jumbo else ""
        image_url = await self._context.resolve_asset_url(node.image_url)
        self._buffer.write(
            f'<img loading="lazy" '
            f'class="chatlog__emoji {jumbo_class}" '
            f'alt="{node.name}" '
            f'title="{node.code}" '
            f'src="{image_url}">'
        )

    # -- mentions --

    async def visit_mention(self, node: MentionNode) -> None:
        ctx = self._context

        if node.kind == MentionKind.EVERYONE:
            self._buffer.write(
                '<span class="chatlog__markdown-mention">@everyone</span>'
            )

        elif node.kind == MentionKind.HERE:
            self._buffer.write(
                '<span class="chatlog__markdown-mention">@here</span>'
            )

        elif node.kind == MentionKind.USER:
            if node.target_id is not None:
                await ctx.populate_member_by_id(node.target_id)

            member = ctx.try_get_member(node.target_id) if node.target_id else None
            if member is not None:
                full_name = member.user.full_name
                display_name = member.display_name or member.user.display_name
            else:
                full_name = "Unknown"
                display_name = "Unknown"

            self._buffer.write(
                f'<span class="chatlog__markdown-mention" '
                f'title="{_html_encode(full_name)}">'
                f"@{_html_encode(display_name)}</span>"
            )

        elif node.kind == MentionKind.CHANNEL:
            channel = ctx.try_get_channel(node.target_id) if node.target_id else None
            if channel and channel.is_voice:
                symbol = "\U0001F50A"  # speaker emoji
            else:
                symbol = "#"
            name = channel.name if channel else "deleted-channel"

            self._buffer.write(
                f'<span class="chatlog__markdown-mention">'
                f"{symbol}{_html_encode(name)}</span>"
            )

        elif node.kind == MentionKind.ROLE:
            role = ctx.try_get_role(node.target_id) if node.target_id else None
            name = role.name if role else "deleted-role"

            style = ""
            if role and role.color:
                # role.color is a hex string like "#ff0000"
                hex_color = role.color.lstrip("#")
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)
                style = (
                    f"color: rgb({r}, {g}, {b}); "
                    f"background-color: rgba({r}, {g}, {b}, 0.1);"
                )

            self._buffer.write(
                f'<span class="chatlog__markdown-mention" style="{style}">'
                f"@{_html_encode(name)}</span>"
            )

    # -- timestamps --

    async def visit_timestamp(self, node: TimestampNode) -> None:
        ctx = self._context

        if node.instant is not None:
            formatted = ctx.format_date(node.instant, node.format or "g")
            formatted_long = ctx.format_date(node.instant, "f")
        else:
            formatted = "Invalid date"
            formatted_long = ""

        self._buffer.write(
            f'<span class="chatlog__markdown-timestamp" '
            f'title="{_html_encode(formatted_long)}">'
            f"{_html_encode(formatted)}</span>"
        )

    # -- static entry point --

    @staticmethod
    async def format(
        context: ExportContext,
        markdown: str,
        is_jumbo_allowed: bool = True,
    ) -> str:
        """Parse *markdown* with the full parser and render as HTML."""
        nodes = parse(markdown)

        # Determine if the message consists solely of emoji (jumbo mode)
        is_jumbo = is_jumbo_allowed and all(
            isinstance(n, EmojiNode)
            or (isinstance(n, TextNode) and not n.text.strip())
            for n in nodes
        )

        buf = StringIO()
        visitor = HtmlMarkdownVisitor(context, buf, is_jumbo)
        await visitor.visit_many(nodes)
        return buf.getvalue()
