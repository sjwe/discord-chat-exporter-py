"""Base markdown visitor (async)."""

from __future__ import annotations

from typing import Sequence

from discord_chat_exporter.core.markdown.nodes import (
    EmojiNode,
    FormattingNode,
    HeadingNode,
    InlineCodeBlockNode,
    LinkNode,
    ListItemNode,
    ListNode,
    MarkdownNode,
    MentionNode,
    MultiLineCodeBlockNode,
    TextNode,
    TimestampNode,
)


class MarkdownVisitor:
    """Abstract visitor that walks a markdown AST.

    Override the ``visit_*`` methods in subclasses to implement custom
    behaviour.  The default implementations for container nodes simply
    recurse into their children.
    """

    # -- leaf visitors (no-ops by default) --

    async def visit_text(self, node: TextNode) -> None:
        pass

    async def visit_emoji(self, node: EmojiNode) -> None:
        pass

    async def visit_mention(self, node: MentionNode) -> None:
        pass

    async def visit_inline_code_block(self, node: InlineCodeBlockNode) -> None:
        pass

    async def visit_multi_line_code_block(self, node: MultiLineCodeBlockNode) -> None:
        pass

    async def visit_timestamp(self, node: TimestampNode) -> None:
        pass

    # -- container visitors (recurse by default) --

    async def visit_formatting(self, node: FormattingNode) -> None:
        await self.visit_many(node.children)

    async def visit_heading(self, node: HeadingNode) -> None:
        await self.visit_many(node.children)

    async def visit_list(self, node: ListNode) -> None:
        await self.visit_many(node.items)

    async def visit_list_item(self, node: ListItemNode) -> None:
        await self.visit_many(node.children)

    async def visit_link(self, node: LinkNode) -> None:
        await self.visit_many(node.children)

    # -- dispatch --

    async def visit(self, node: MarkdownNode) -> None:
        if isinstance(node, TextNode):
            await self.visit_text(node)
        elif isinstance(node, FormattingNode):
            await self.visit_formatting(node)
        elif isinstance(node, HeadingNode):
            await self.visit_heading(node)
        elif isinstance(node, ListNode):
            await self.visit_list(node)
        elif isinstance(node, ListItemNode):
            await self.visit_list_item(node)
        elif isinstance(node, InlineCodeBlockNode):
            await self.visit_inline_code_block(node)
        elif isinstance(node, MultiLineCodeBlockNode):
            await self.visit_multi_line_code_block(node)
        elif isinstance(node, LinkNode):
            await self.visit_link(node)
        elif isinstance(node, EmojiNode):
            await self.visit_emoji(node)
        elif isinstance(node, MentionNode):
            await self.visit_mention(node)
        elif isinstance(node, TimestampNode):
            await self.visit_timestamp(node)
        else:
            raise TypeError(f"Unknown markdown node type: {type(node).__name__}")

    async def visit_many(self, nodes: Sequence[MarkdownNode]) -> None:
        for node in nodes:
            await self.visit(node)
