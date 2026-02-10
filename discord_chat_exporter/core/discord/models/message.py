"""Message model and related types."""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum, IntFlag
from typing import Iterator

from pydantic import BaseModel, model_validator

from discord_chat_exporter.core.discord.models.attachment import Attachment
from discord_chat_exporter.core.discord.models.embed import Embed
from discord_chat_exporter.core.discord.models.interaction import Interaction
from discord_chat_exporter.core.discord.models.reaction import Reaction
from discord_chat_exporter.core.discord.models.sticker import Sticker
from discord_chat_exporter.core.discord.models.user import User
from discord_chat_exporter.core.discord.snowflake import Snowflake


class MessageKind(IntEnum):
    DEFAULT = 0
    RECIPIENT_ADD = 1
    RECIPIENT_REMOVE = 2
    CALL = 3
    CHANNEL_NAME_CHANGE = 4
    CHANNEL_ICON_CHANGE = 5
    CHANNEL_PINNED_MESSAGE = 6
    GUILD_MEMBER_JOIN = 7
    THREAD_CREATED = 18
    REPLY = 19


class MessageFlags(IntFlag):
    NONE = 0
    CROSS_POSTED = 1
    CROSS_POST = 2
    SUPPRESS_EMBEDS = 4
    SOURCE_MESSAGE_DELETED = 8
    URGENT = 16
    HAS_THREAD = 32
    EPHEMERAL = 64
    LOADING = 128


class MessageReference(BaseModel):
    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    message_id: Snowflake | None = None
    channel_id: Snowflake | None = None
    guild_id: Snowflake | None = None

    @model_validator(mode="before")
    @classmethod
    def _from_api(cls, data: dict) -> dict:  # type: ignore[override]
        if isinstance(data.get("message_id"), Snowflake | None) and "channel_id" in data:
            return data
        return {
            "message_id": (
                Snowflake.parse(str(data["message_id"])) if data.get("message_id") else None
            ),
            "channel_id": (
                Snowflake.parse(str(data["channel_id"])) if data.get("channel_id") else None
            ),
            "guild_id": (
                Snowflake.parse(str(data["guild_id"])) if data.get("guild_id") else None
            ),
        }


class Message(BaseModel):
    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    id: Snowflake
    kind: MessageKind
    flags: MessageFlags = MessageFlags.NONE
    author: User
    timestamp: datetime
    edited_timestamp: datetime | None = None
    call_ended_timestamp: datetime | None = None
    is_pinned: bool = False
    content: str = ""
    attachments: list[Attachment] = []
    embeds: list[Embed] = []
    stickers: list[Sticker] = []
    reactions: list[Reaction] = []
    mentioned_users: list[User] = []
    reference: MessageReference | None = None
    referenced_message: Message | None = None
    interaction: Interaction | None = None

    @property
    def is_system_notification(self) -> bool:
        return MessageKind.RECIPIENT_ADD <= self.kind <= MessageKind.THREAD_CREATED

    @property
    def is_reply(self) -> bool:
        return self.kind == MessageKind.REPLY

    @property
    def is_reply_like(self) -> bool:
        return self.is_reply or self.interaction is not None

    @property
    def is_empty(self) -> bool:
        return (
            not self.content.strip()
            and not self.attachments
            and not self.embeds
            and not self.stickers
        )

    def get_referenced_users(self) -> Iterator[User]:
        yield self.author
        yield from self.mentioned_users
        if self.referenced_message is not None:
            yield self.referenced_message.author
        if self.interaction is not None:
            yield self.interaction.user

    @classmethod
    def _normalize_embeds(cls, embeds: list[Embed]) -> list[Embed]:
        """Merge consecutive Twitter embeds with same URL into one (multi-image)."""
        if len(embeds) <= 1:
            return embeds

        normalized: list[Embed] = []
        i = 0
        while i < len(embeds):
            embed = embeds[i]
            if embed.url and "://twitter.com/" in (embed.url or ""):
                trailing: list[Embed] = []
                j = i + 1
                while j < len(embeds):
                    e = embeds[j]
                    if (
                        e.url == embed.url
                        and e.timestamp is None
                        and e.author is None
                        and e.color is None
                        and not (e.description or "").strip()
                        and not e.fields
                        and len(e.images) == 1
                        and e.footer is None
                    ):
                        trailing.append(e)
                        j += 1
                    else:
                        break

                if trailing:
                    all_images = list(embed.images)
                    for te in trailing:
                        all_images.extend(te.images)
                    normalized.append(embed.model_copy(update={"images": all_images}))
                    i = j
                else:
                    normalized.append(embed)
                    i += 1
            else:
                normalized.append(embed)
                i += 1

        return normalized

    @model_validator(mode="before")
    @classmethod
    def _from_api(cls, data: dict) -> dict:  # type: ignore[override]
        if isinstance(data.get("kind"), MessageKind):
            return data

        mid = Snowflake.parse(str(data["id"]))
        kind = MessageKind(data["type"])
        flags = MessageFlags(data.get("flags", 0))
        author = User.model_validate(data["author"])
        timestamp = data["timestamp"]
        edited_timestamp = data.get("edited_timestamp")

        call_data = data.get("call")
        call_ended_timestamp = call_data.get("ended_timestamp") if call_data else None

        is_pinned = data.get("pinned", False)
        content = data.get("content", "")

        attachments = [Attachment.model_validate(a) for a in data.get("attachments", [])]
        embeds = cls._normalize_embeds(
            [Embed.model_validate(e) for e in data.get("embeds", [])]
        )
        stickers = [Sticker.model_validate(s) for s in data.get("sticker_items", [])]
        reactions = [Reaction.model_validate(r) for r in data.get("reactions", [])]
        mentioned_users = [User.model_validate(u) for u in data.get("mentions", [])]

        reference = (
            MessageReference.model_validate(data["message_reference"])
            if data.get("message_reference")
            else None
        )
        referenced_message = (
            Message.model_validate(data["referenced_message"])
            if data.get("referenced_message")
            else None
        )
        interaction = (
            Interaction.model_validate(data["interaction"])
            if data.get("interaction")
            else None
        )

        return {
            "id": mid,
            "kind": kind,
            "flags": flags,
            "author": author,
            "timestamp": timestamp,
            "edited_timestamp": edited_timestamp,
            "call_ended_timestamp": call_ended_timestamp,
            "is_pinned": is_pinned,
            "content": content,
            "attachments": attachments,
            "embeds": embeds,
            "stickers": stickers,
            "reactions": reactions,
            "mentioned_users": mentioned_users,
            "reference": reference,
            "referenced_message": referenced_message,
            "interaction": interaction,
        }
