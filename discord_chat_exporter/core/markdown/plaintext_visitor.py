"""Plain text markdown visitor - strips formatting, resolves mentions."""

from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING

from discord_chat_exporter.core.markdown.nodes import (
    EmojiNode,
    MentionKind,
    MentionNode,
    TextNode,
    TimestampNode,
)
from discord_chat_exporter.core.markdown.parser import parse_minimal
from discord_chat_exporter.core.markdown.visitor import MarkdownVisitor

if TYPE_CHECKING:
    from discord_chat_exporter.core.exporting.context import ExportContext


class PlainTextMarkdownVisitor(MarkdownVisitor):
    """Renders a markdown AST as plain text.

    Uses the minimal parser (only mentions, custom emoji, timestamps)
    because plain text does not need formatting, links, or standard emoji.
    """

    def __init__(self, context: ExportContext, buffer: StringIO) -> None:
        self._context = context
        self._buffer = buffer

    # -- text --

    async def visit_text(self, node: TextNode) -> None:
        self._buffer.write(node.text)

    # -- emoji --

    async def visit_emoji(self, node: EmojiNode) -> None:
        if node.is_custom_emoji:
            self._buffer.write(f":{node.name}:")
        else:
            self._buffer.write(node.name)

    # -- mentions --

    async def visit_mention(self, node: MentionNode) -> None:
        ctx = self._context

        if node.kind == MentionKind.EVERYONE:
            self._buffer.write("@everyone")

        elif node.kind == MentionKind.HERE:
            self._buffer.write("@here")

        elif node.kind == MentionKind.USER:
            if node.target_id is not None:
                await ctx.populate_member_by_id(node.target_id)
            member = ctx.try_get_member(node.target_id) if node.target_id else None
            if member is not None:
                display_name = member.display_name or member.user.display_name
            else:
                display_name = "Unknown"
            self._buffer.write(f"@{display_name}")

        elif node.kind == MentionKind.CHANNEL:
            channel = ctx.try_get_channel(node.target_id) if node.target_id else None
            name = channel.name if channel else "deleted-channel"
            self._buffer.write(f"#{name}")
            if channel and channel.is_voice:
                self._buffer.write(" [voice]")

        elif node.kind == MentionKind.ROLE:
            role = ctx.try_get_role(node.target_id) if node.target_id else None
            name = role.name if role else "deleted-role"
            self._buffer.write(f"@{name}")

    # -- timestamps --

    async def visit_timestamp(self, node: TimestampNode) -> None:
        if node.instant is not None:
            fmt = node.format or "g"
            self._buffer.write(self._context.format_date(node.instant, fmt))
        else:
            self._buffer.write("Invalid date")

    # -- static entry point --

    @staticmethod
    async def format(context: ExportContext, markdown: str) -> str:
        """Parse *markdown* with the minimal parser and render as plain text."""
        nodes = parse_minimal(markdown)
        buf = StringIO()
        visitor = PlainTextMarkdownVisitor(context, buf)
        await visitor.visit_many(nodes)
        return buf.getvalue()
