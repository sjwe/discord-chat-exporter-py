"""Discord markdown AST node types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Sequence

from discord_chat_exporter.core.discord.snowflake import Snowflake


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class FormattingKind(Enum):
    BOLD = "bold"
    ITALIC = "italic"
    UNDERLINE = "underline"
    STRIKETHROUGH = "strikethrough"
    SPOILER = "spoiler"
    QUOTE = "quote"


class MentionKind(Enum):
    EVERYONE = "everyone"
    HERE = "here"
    USER = "user"
    CHANNEL = "channel"
    ROLE = "role"


# ---------------------------------------------------------------------------
# Base node
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MarkdownNode:
    """Abstract base for every markdown AST node."""


# ---------------------------------------------------------------------------
# Concrete nodes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TextNode(MarkdownNode):
    text: str


@dataclass(frozen=True)
class FormattingNode(MarkdownNode):
    kind: FormattingKind
    children: Sequence[MarkdownNode]


@dataclass(frozen=True)
class HeadingNode(MarkdownNode):
    level: int
    children: Sequence[MarkdownNode]


@dataclass(frozen=True)
class ListItemNode(MarkdownNode):
    children: Sequence[MarkdownNode]


@dataclass(frozen=True)
class ListNode(MarkdownNode):
    items: Sequence[ListItemNode]


@dataclass(frozen=True)
class InlineCodeBlockNode(MarkdownNode):
    code: str


@dataclass(frozen=True)
class MultiLineCodeBlockNode(MarkdownNode):
    language: str
    code: str


@dataclass(frozen=True)
class LinkNode(MarkdownNode):
    url: str
    children: Sequence[MarkdownNode] = field(default_factory=list)

    def __post_init__(self) -> None:
        # If no children provided, default to a TextNode with the URL
        if not self.children:
            object.__setattr__(self, "children", [TextNode(self.url)])


@dataclass(frozen=True)
class MentionNode(MarkdownNode):
    target_id: Snowflake | None
    kind: MentionKind


@dataclass(frozen=True)
class EmojiNode(MarkdownNode):
    # Only present on custom emoji
    id: Snowflake | None
    # Name of custom emoji (e.g. LUL) or actual representation of standard emoji (e.g. the emoji char)
    name: str
    is_animated: bool = False

    @property
    def is_custom_emoji(self) -> bool:
        return self.id is not None

    @property
    def code(self) -> str:
        """Name of custom emoji (e.g. LUL) or short code of standard emoji (e.g. slight_smile)."""
        if self.id is not None:
            return self.name
        # Lazy import to avoid circular / heavy import at module level
        from discord_chat_exporter.core.discord.models.emoji import Emoji

        emoji = Emoji(id=None, name=self.name, is_animated=False)
        return emoji.code

    @property
    def image_url(self) -> str:
        from discord_chat_exporter.core.discord.models.emoji import Emoji

        emoji = Emoji(id=self.id, name=self.name, is_animated=self.is_animated)
        return emoji.image_url


@dataclass(frozen=True)
class TimestampNode(MarkdownNode):
    instant: datetime | None
    format: str | None


# Sentinel for invalid timestamps
TIMESTAMP_INVALID = TimestampNode(instant=None, format=None)


# ---------------------------------------------------------------------------
# Container check helper
# ---------------------------------------------------------------------------


def get_children(node: MarkdownNode) -> Sequence[MarkdownNode] | None:
    """Return the children of a container node, or None if it is a leaf."""
    if isinstance(node, (FormattingNode, HeadingNode, ListItemNode, LinkNode)):
        return node.children
    return None
