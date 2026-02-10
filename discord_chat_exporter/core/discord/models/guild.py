"""Guild (server) model."""

from __future__ import annotations

from pydantic import BaseModel, model_validator

from discord_chat_exporter.core.discord.models.cdn import ImageCdn
from discord_chat_exporter.core.discord.snowflake import Snowflake


class Guild(BaseModel):
    model_config = {"frozen": True}

    id: Snowflake
    name: str
    icon_url: str

    @property
    def is_direct(self) -> bool:
        return self.id == Snowflake.ZERO

    @model_validator(mode="before")
    @classmethod
    def _from_api(cls, data: dict) -> dict:  # type: ignore[override]
        if "icon_url" in data:
            return data
        gid = Snowflake.parse(str(data["id"]))
        icon_hash = data.get("icon")
        icon_url = (
            ImageCdn.get_guild_icon_url(gid, icon_hash)
            if icon_hash
            else ImageCdn.get_fallback_user_avatar_url()
        )
        return {"id": gid, "name": data["name"], "icon_url": icon_url}


Guild.DIRECT_MESSAGES = Guild(
    id=Snowflake.ZERO,
    name="Direct Messages",
    icon_url=ImageCdn.get_fallback_user_avatar_url(),
)
