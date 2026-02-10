"""User model."""

from __future__ import annotations

from pydantic import BaseModel, model_validator

from discord_chat_exporter.core.discord.models.cdn import ImageCdn
from discord_chat_exporter.core.discord.snowflake import Snowflake


class User(BaseModel):
    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    id: Snowflake
    is_bot: bool = False
    discriminator: int | None = None
    name: str
    display_name: str
    avatar_url: str

    @property
    def discriminator_formatted(self) -> str:
        return f"{self.discriminator:04d}" if self.discriminator is not None else "0000"

    @property
    def full_name(self) -> str:
        if self.discriminator is not None:
            return f"{self.name}#{self.discriminator_formatted}"
        return self.name

    @model_validator(mode="before")
    @classmethod
    def _from_api(cls, data: dict) -> dict:  # type: ignore[override]
        if "avatar_url" in data and "display_name" in data:
            return data

        uid = Snowflake.parse(str(data["id"]))
        is_bot = data.get("bot", False)

        disc_raw = data.get("discriminator")
        discriminator = int(disc_raw) if disc_raw and disc_raw.strip() else None
        if discriminator == 0:
            discriminator = None

        name = data.get("username", "")
        display_name = data.get("global_name") or name

        avatar_index = (
            discriminator % 5 if discriminator else int((uid.value >> 22) % 6)
        )
        avatar_hash = data.get("avatar")
        avatar_url = (
            ImageCdn.get_user_avatar_url(uid, avatar_hash)
            if avatar_hash
            else ImageCdn.get_fallback_user_avatar_url(avatar_index)
        )

        return {
            "id": uid,
            "is_bot": is_bot,
            "discriminator": discriminator,
            "name": name,
            "display_name": display_name,
            "avatar_url": avatar_url,
        }
