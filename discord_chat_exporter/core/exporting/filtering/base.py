"""Base message filter classes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from discord_chat_exporter.core.discord.models.message import Message


class MessageFilter(ABC):
    """Abstract base class for message filters.

    Subclasses implement ``is_match`` to decide whether a given message
    passes the filter criteria.
    """

    @abstractmethod
    def is_match(self, message: Message) -> bool:
        """Return ``True`` if *message* satisfies this filter."""

    # Convenience factory --------------------------------------------------

    @staticmethod
    def null() -> MessageFilter:
        """Return a filter that matches every message."""
        return NullMessageFilter()

    @staticmethod
    def parse(text: str) -> MessageFilter:
        """Parse a filter DSL string and return the corresponding filter tree.

        See :func:`~discord_chat_exporter.core.exporting.filtering.parser.parse_filter`
        for the grammar description.
        """
        # Import here to avoid circular imports.
        from discord_chat_exporter.core.exporting.filtering.parser import (
            parse_filter,
        )

        return parse_filter(text)


class NullMessageFilter(MessageFilter):
    """A filter that unconditionally matches every message."""

    def is_match(self, message: Message) -> bool:
        return True
