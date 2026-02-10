"""Concrete leaf-level message filters.

Each filter tests a single aspect of a :class:`Message` and is typically
produced by the filter DSL parser.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import TYPE_CHECKING

from discord_chat_exporter.core.exporting.filtering.base import MessageFilter

if TYPE_CHECKING:
    from discord_chat_exporter.core.discord.models.message import Message


# ---------------------------------------------------------------------------
# ContainsMessageFilter
# ---------------------------------------------------------------------------

# Regex used by HasMessageFilter to extract URLs from message content.
# Mirrors the auto-link / hidden-link / masked-link patterns from the C#
# MarkdownParser that powers ``MarkdownParser.ExtractLinks``.
_URL_RE = re.compile(r"https?://\S*[^.,;:\"'\s]")


class ContainsMessageFilter(MessageFilter):
    """Match messages whose content (or embed text) contains *text*.

    The match is performed against word boundaries so that ``"max"`` does
    **not** match ``"maximum"`` but **does** match ``"(max)"``.  See
    `<https://github.com/Tyrrrz/DiscordChatExporter/issues/909>`_.
    """

    def __init__(self, text: str) -> None:
        self._text = text
        # Build the pattern once and reuse it.
        self._pattern = re.compile(
            r"(?:\b|\s|^)" + re.escape(text) + r"(?:\b|\s|$)",
            re.IGNORECASE,
        )

    def _content_matches(self, content: str | None) -> bool:
        if not content or not content.strip():
            return False
        return self._pattern.search(content) is not None

    def is_match(self, message: Message) -> bool:
        if self._content_matches(message.content):
            return True
        for embed in message.embeds:
            if (
                self._content_matches(embed.title)
                or self._content_matches(
                    embed.author.name if embed.author else None
                )
                or self._content_matches(embed.description)
                or self._content_matches(
                    embed.footer.text if embed.footer else None
                )
                or any(
                    self._content_matches(f.name)
                    or self._content_matches(f.value)
                    for f in embed.fields
                )
            ):
                return True
        return False


# ---------------------------------------------------------------------------
# FromMessageFilter
# ---------------------------------------------------------------------------


class FromMessageFilter(MessageFilter):
    """Match messages whose author matches *value*.

    The comparison is case-insensitive and checks the author's ``name``,
    ``display_name``, ``full_name``, and ``id``.
    """

    def __init__(self, value: str) -> None:
        self._value = value

    def is_match(self, message: Message) -> bool:
        v = self._value.lower()
        author = message.author
        return (
            author.name.lower() == v
            or author.display_name.lower() == v
            or author.full_name.lower() == v
            or str(author.id).lower() == v
        )


# ---------------------------------------------------------------------------
# HasMessageFilter
# ---------------------------------------------------------------------------


class MessageContentMatchKind(Enum):
    """Kinds of content that can be checked with ``has:<kind>``."""

    LINK = "link"
    EMBED = "embed"
    FILE = "file"
    VIDEO = "video"
    IMAGE = "image"
    SOUND = "sound"
    PIN = "pin"
    INVITE = "invite"


# Map from DSL token to enum value.
_HAS_KIND_MAP: dict[str, MessageContentMatchKind] = {
    k.value: k for k in MessageContentMatchKind
}


def _parse_has_kind(text: str) -> MessageContentMatchKind:
    """Resolve a string like ``"link"`` into a :class:`MessageContentMatchKind`."""
    kind = _HAS_KIND_MAP.get(text.lower())
    if kind is None:
        raise ValueError(
            f"Unknown 'has:' kind {text!r}. "
            f"Expected one of: {', '.join(_HAS_KIND_MAP)}"
        )
    return kind


class HasMessageFilter(MessageFilter):
    """Match messages that contain a specific kind of content."""

    def __init__(self, kind: MessageContentMatchKind | str) -> None:
        if isinstance(kind, str):
            kind = _parse_has_kind(kind)
        self._kind = kind

    def is_match(self, message: Message) -> bool:
        kind = self._kind
        if kind is MessageContentMatchKind.LINK:
            return bool(_URL_RE.search(message.content))
        if kind is MessageContentMatchKind.EMBED:
            return len(message.embeds) > 0
        if kind is MessageContentMatchKind.FILE:
            return len(message.attachments) > 0
        if kind is MessageContentMatchKind.VIDEO:
            return any(a.is_video for a in message.attachments)
        if kind is MessageContentMatchKind.IMAGE:
            return any(a.is_image for a in message.attachments)
        if kind is MessageContentMatchKind.SOUND:
            return any(a.is_audio for a in message.attachments)
        if kind is MessageContentMatchKind.PIN:
            return message.is_pinned
        if kind is MessageContentMatchKind.INVITE:
            from discord_chat_exporter.core.discord.client import Invite

            urls = _URL_RE.findall(message.content)
            return any(
                Invite.try_get_code_from_url(url) is not None for url in urls
            )
        raise ValueError(f"Unknown message content match kind {kind!r}.")


# ---------------------------------------------------------------------------
# MentionsMessageFilter
# ---------------------------------------------------------------------------


class MentionsMessageFilter(MessageFilter):
    """Match messages that mention a user matching *value*."""

    def __init__(self, value: str) -> None:
        self._value = value

    def is_match(self, message: Message) -> bool:
        v = self._value.lower()
        return any(
            user.name.lower() == v
            or user.display_name.lower() == v
            or user.full_name.lower() == v
            or str(user.id).lower() == v
            for user in message.mentioned_users
        )


# ---------------------------------------------------------------------------
# ReactionMessageFilter
# ---------------------------------------------------------------------------


class ReactionMessageFilter(MessageFilter):
    """Match messages that have a reaction matching *value*."""

    def __init__(self, value: str) -> None:
        self._value = value

    def is_match(self, message: Message) -> bool:
        v = self._value.lower()
        return any(
            (
                (r.emoji.id is not None and str(r.emoji.id).lower() == v)
                or r.emoji.name.lower() == v
                or r.emoji.code.lower() == v
            )
            for r in message.reactions
        )
