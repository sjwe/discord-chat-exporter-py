"""Guild member model."""

from __future__ import annotations

from pydantic import BaseModel, model_validator

from discord_chat_exporter.core.discord.models.cdn import ImageCdn
from discord_chat_exporter.core.discord.models.user import User
from discord_chat_exporter.core.discord.snowflake import Snowflake


class Member(BaseModel):
    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    user: User
    display_name: str | None = None
    avatar_url: str | None = None
    role_ids: list[Snowflake] = []

    @property
    def id(self) -> Snowflake:
        return self.user.id

    @classmethod
    def create_fallback(cls, user: User) -> Member:
        return cls(user=user, display_name=None, avatar_url=None, role_ids=[])

    @model_validator(mode="before")
    @classmethod
    def _from_api(cls, data: dict) -> dict:  # type: ignore[override]
        if isinstance(data.get("user"), User):
            return data

        user = User.model_validate(data["user"])
        display_name = data.get("nick")
        if display_name and not display_name.strip():
            display_name = None

        role_ids = [Snowflake.parse(str(r)) for r in data.get("roles", [])]

        guild_id = data.get("_guild_id")
        avatar_hash = data.get("avatar")
        avatar_url = (
            ImageCdn.get_member_avatar_url(guild_id, user.id, avatar_hash)
            if guild_id and avatar_hash
            else None
        )

        return {
            "user": user,
            "display_name": display_name,
            "avatar_url": avatar_url,
            "role_ids": role_ids,
        }
