"""Custom exceptions for DiscordChatExporter."""

from __future__ import annotations


class DiscordChatExporterError(Exception):
    """Base exception for all DiscordChatExporter errors.

    Attributes:
        is_fatal: If True, the error is unrecoverable and the user should be
                  prompted to take corrective action (e.g. invalid token).
    """

    def __init__(
        self,
        message: str,
        is_fatal: bool = False,
        *args: object,
    ) -> None:
        super().__init__(message, *args)
        self.is_fatal = is_fatal


class ChannelEmptyError(DiscordChatExporterError):
    """Raised when a channel has no messages in the requested range."""
