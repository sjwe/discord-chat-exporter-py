"""Combinator filters that compose other filters."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from discord_chat_exporter.core.exporting.filtering.base import MessageFilter

if TYPE_CHECKING:
    from discord_chat_exporter.core.discord.models.message import Message


class BinaryExpressionKind(Enum):
    """The kind of binary expression connecting two filters."""

    OR = "or"
    AND = "and"


class BinaryExpressionMessageFilter(MessageFilter):
    """Combine two filters with a logical AND or OR."""

    def __init__(
        self,
        first: MessageFilter,
        second: MessageFilter,
        kind: BinaryExpressionKind,
    ) -> None:
        self._first = first
        self._second = second
        self._kind = kind

    def is_match(self, message: Message) -> bool:
        if self._kind is BinaryExpressionKind.OR:
            return self._first.is_match(message) or self._second.is_match(
                message
            )
        if self._kind is BinaryExpressionKind.AND:
            return self._first.is_match(message) and self._second.is_match(
                message
            )
        raise ValueError(
            f"Unknown binary expression kind {self._kind!r}."
        )


class NegatedMessageFilter(MessageFilter):
    """Negate an inner filter."""

    def __init__(self, inner: MessageFilter) -> None:
        self._inner = inner

    def is_match(self, message: Message) -> bool:
        return not self._inner.is_match(message)
