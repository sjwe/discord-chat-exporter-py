"""Attachment model."""

from __future__ import annotations

from pathlib import PurePosixPath

from pydantic import BaseModel, model_validator

from discord_chat_exporter.core.discord.snowflake import Snowflake

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
_VIDEO_EXTS = {".gifv", ".mp4", ".webm", ".mov"}
_AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}


class Attachment(BaseModel):
    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    id: Snowflake
    url: str
    file_name: str
    description: str | None = None
    width: int | None = None
    height: int | None = None
    file_size_bytes: int = 0

    @property
    def file_extension(self) -> str:
        return PurePosixPath(self.file_name).suffix.lower()

    @property
    def is_image(self) -> bool:
        return self.file_extension in _IMAGE_EXTS

    @property
    def is_video(self) -> bool:
        return self.file_extension in _VIDEO_EXTS

    @property
    def is_audio(self) -> bool:
        return self.file_extension in _AUDIO_EXTS

    @property
    def is_spoiler(self) -> bool:
        return self.file_name.startswith("SPOILER_")

    @property
    def file_size_display(self) -> str:
        b = self.file_size_bytes
        if abs(b) >= 1024**3:
            return f"{b / 1024**3:.2f} GB"
        if abs(b) >= 1024**2:
            return f"{b / 1024**2:.2f} MB"
        if abs(b) >= 1024:
            return f"{b / 1024:.2f} KB"
        return f"{b} bytes"

    @model_validator(mode="before")
    @classmethod
    def _from_api(cls, data: dict) -> dict:  # type: ignore[override]
        if "file_name" in data:
            return data
        return {
            "id": Snowflake.parse(str(data["id"])),
            "url": data["url"],
            "file_name": data["filename"],
            "description": data.get("description"),
            "width": data.get("width"),
            "height": data.get("height"),
            "file_size_bytes": data.get("size", 0),
        }
