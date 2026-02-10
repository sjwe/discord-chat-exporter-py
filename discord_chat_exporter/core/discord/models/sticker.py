"""Sticker model."""

from __future__ import annotations

from enum import IntEnum

from pydantic import BaseModel, model_validator

from discord_chat_exporter.core.discord.models.cdn import ImageCdn
from discord_chat_exporter.core.discord.snowflake import Snowflake


class StickerFormat(IntEnum):
    PNG = 1
    APNG = 2
    LOTTIE = 3
    GIF = 4


class Sticker(BaseModel):
    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    id: Snowflake
    name: str
    format: StickerFormat
    source_url: str

    @property
    def is_image(self) -> bool:
        return self.format != StickerFormat.LOTTIE

    @model_validator(mode="before")
    @classmethod
    def _from_api(cls, data: dict) -> dict:  # type: ignore[override]
        if "source_url" in data:
            return data

        sid = Snowflake.parse(str(data["id"]))
        name = data["name"]
        fmt = StickerFormat(data["format_type"])

        ext_map = {
            StickerFormat.PNG: "png",
            StickerFormat.APNG: "png",
            StickerFormat.LOTTIE: "json",
            StickerFormat.GIF: "gif",
        }
        source_url = ImageCdn.get_sticker_url(sid, ext_map[fmt])

        return {"id": sid, "name": name, "format": fmt, "source_url": source_url}
