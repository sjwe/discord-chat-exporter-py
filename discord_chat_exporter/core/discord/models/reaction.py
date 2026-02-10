"""Reaction model."""

from __future__ import annotations

from pydantic import BaseModel, model_validator

from discord_chat_exporter.core.discord.models.emoji import Emoji


class Reaction(BaseModel):
    model_config = {"frozen": True}

    emoji: Emoji
    count: int

    @model_validator(mode="before")
    @classmethod
    def _from_api(cls, data: dict) -> dict:  # type: ignore[override]
        if isinstance(data.get("emoji"), Emoji):
            return data
        return {
            "emoji": Emoji.model_validate(data["emoji"]),
            "count": data["count"],
        }
