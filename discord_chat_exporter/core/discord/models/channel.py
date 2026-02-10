"""Channel model and ChannelKind enum."""

from __future__ import annotations

from enum import IntEnum

from pydantic import BaseModel, model_validator

from discord_chat_exporter.core.discord.models.cdn import ImageCdn
from discord_chat_exporter.core.discord.snowflake import Snowflake


class ChannelKind(IntEnum):
    GUILD_TEXT_CHAT = 0
    DIRECT_TEXT_CHAT = 1
    GUILD_VOICE_CHAT = 2
    DIRECT_GROUP_TEXT_CHAT = 3
    GUILD_CATEGORY = 4
    GUILD_NEWS = 5
    GUILD_NEWS_THREAD = 10
    GUILD_PUBLIC_THREAD = 11
    GUILD_PRIVATE_THREAD = 12
    GUILD_STAGE_VOICE = 13
    GUILD_DIRECTORY = 14
    GUILD_FORUM = 15


class Channel(BaseModel):
    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    id: Snowflake
    kind: ChannelKind
    guild_id: Snowflake
    parent: Channel | None = None
    name: str
    position: int | None = None
    icon_url: str | None = None
    topic: str | None = None
    is_archived: bool = False
    last_message_id: Snowflake | None = None

    @property
    def is_direct(self) -> bool:
        return self.kind in (ChannelKind.DIRECT_TEXT_CHAT, ChannelKind.DIRECT_GROUP_TEXT_CHAT)

    @property
    def is_guild(self) -> bool:
        return not self.is_direct

    @property
    def is_category(self) -> bool:
        return self.kind == ChannelKind.GUILD_CATEGORY

    @property
    def is_voice(self) -> bool:
        return self.kind in (ChannelKind.GUILD_VOICE_CHAT, ChannelKind.GUILD_STAGE_VOICE)

    @property
    def is_thread(self) -> bool:
        return self.kind in (
            ChannelKind.GUILD_NEWS_THREAD,
            ChannelKind.GUILD_PUBLIC_THREAD,
            ChannelKind.GUILD_PRIVATE_THREAD,
        )

    @property
    def is_empty(self) -> bool:
        return self.last_message_id is None

    def get_parents(self) -> list[Channel]:
        parents: list[Channel] = []
        current = self.parent
        while current is not None:
            parents.append(current)
            current = current.parent
        return parents

    def try_get_root_parent(self) -> Channel | None:
        parents = self.get_parents()
        return parents[-1] if parents else None

    def get_hierarchical_name(self) -> str:
        parts = [p.name for p in reversed(self.get_parents())]
        parts.append(self.name)
        return " / ".join(parts)

    def may_have_messages_after(self, message_id: Snowflake) -> bool:
        return not self.is_empty and message_id < self.last_message_id  # type: ignore[operator]

    def may_have_messages_before(self, message_id: Snowflake) -> bool:
        return not self.is_empty and message_id > self.id

    @model_validator(mode="before")
    @classmethod
    def _from_api(cls, data: dict) -> dict:  # type: ignore[override]
        if "kind" in data:
            return data
        cid = Snowflake.parse(str(data["id"]))
        kind = ChannelKind(data["type"])

        guild_id = (
            Snowflake.parse(str(data["guild_id"]))
            if data.get("guild_id")
            else Snowflake.ZERO
        )

        # Name: guild channel name, or DM recipients, or fallback to ID
        name = data.get("name")
        if not name:
            recipients = data.get("recipients", [])
            if recipients:
                from discord_chat_exporter.core.discord.models.user import User

                users = sorted(
                    (User.model_validate(r) for r in recipients),
                    key=lambda u: u.id.value,
                )
                name = ", ".join(u.display_name for u in users)
            else:
                name = str(cid)

        position = data.get("position")
        icon_hash = data.get("icon")
        icon_url = ImageCdn.get_channel_icon_url(cid, icon_hash) if icon_hash else None
        topic = data.get("topic")

        thread_meta = data.get("thread_metadata", {})
        is_archived = thread_meta.get("archived", False) if thread_meta else False

        last_msg_raw = data.get("last_message_id")
        last_message_id = Snowflake.parse(str(last_msg_raw)) if last_msg_raw else None

        return {
            "id": cid,
            "kind": kind,
            "guild_id": guild_id,
            "parent": data.get("parent"),
            "name": name,
            "position": position,
            "icon_url": icon_url,
            "topic": topic,
            "is_archived": is_archived,
            "last_message_id": last_message_id,
        }
