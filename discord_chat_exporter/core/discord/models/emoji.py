"""Emoji model."""

from __future__ import annotations

from pydantic import BaseModel, model_validator

from discord_chat_exporter.core.discord.models.cdn import ImageCdn
from discord_chat_exporter.core.discord.snowflake import Snowflake


class Emoji(BaseModel):
    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    id: Snowflake | None = None
    name: str
    is_animated: bool = False

    @property
    def is_custom_emoji(self) -> bool:
        return self.id is not None

    @property
    def code(self) -> str:
        if self.id is not None:
            return self.name
        from discord_chat_exporter.core.discord.models.emoji_index import EMOJI_TO_CODE

        return EMOJI_TO_CODE.get(self.name, self.name)

    @property
    def image_url(self) -> str:
        if self.id is not None:
            return ImageCdn.get_custom_emoji_url(self.id, self.is_animated)
        return ImageCdn.get_standard_emoji_url(self.name)

    @model_validator(mode="before")
    @classmethod
    def _from_api(cls, data: dict) -> dict:  # type: ignore[override]
        if isinstance(data.get("id"), Snowflake | None) and "is_animated" in data:
            return data

        eid_raw = data.get("id")
        eid = Snowflake.parse(str(eid_raw)) if eid_raw else None
        name = data.get("name") or "Unknown Emoji"
        is_animated = data.get("animated", False)

        return {"id": eid, "name": name, "is_animated": is_animated}
