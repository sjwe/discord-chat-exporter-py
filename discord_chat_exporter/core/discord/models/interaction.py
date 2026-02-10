"""Interaction model."""

from __future__ import annotations

from pydantic import BaseModel, model_validator

from discord_chat_exporter.core.discord.models.user import User
from discord_chat_exporter.core.discord.snowflake import Snowflake


class Interaction(BaseModel):
    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    id: Snowflake
    name: str
    user: User

    @model_validator(mode="before")
    @classmethod
    def _from_api(cls, data: dict) -> dict:  # type: ignore[override]
        if isinstance(data.get("user"), User):
            return data
        return {
            "id": Snowflake.parse(str(data["id"])),
            "name": data["name"],
            "user": User.model_validate(data["user"]),
        }
