"""Message filtering DSL for Discord chat exports."""

from discord_chat_exporter.core.exporting.filtering.base import (
    MessageFilter,
    NullMessageFilter,
)
from discord_chat_exporter.core.exporting.filtering.combinators import (
    BinaryExpressionKind,
    BinaryExpressionMessageFilter,
    NegatedMessageFilter,
)
from discord_chat_exporter.core.exporting.filtering.filters import (
    ContainsMessageFilter,
    FromMessageFilter,
    HasMessageFilter,
    MentionsMessageFilter,
    MessageContentMatchKind,
    ReactionMessageFilter,
)
from discord_chat_exporter.core.exporting.filtering.parser import (
    FilterParseError,
    parse_filter,
)

__all__ = [
    "BinaryExpressionKind",
    "BinaryExpressionMessageFilter",
    "ContainsMessageFilter",
    "FilterParseError",
    "FromMessageFilter",
    "HasMessageFilter",
    "MentionsMessageFilter",
    "MessageContentMatchKind",
    "MessageFilter",
    "NegatedMessageFilter",
    "NullMessageFilter",
    "ReactionMessageFilter",
    "parse_filter",
]
