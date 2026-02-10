"""Role model."""

from __future__ import annotations

from pydantic import BaseModel, model_validator

from discord_chat_exporter.core.discord.snowflake import Snowflake


class Role(BaseModel):
    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    id: Snowflake
    name: str
    position: int
    color: str | None = None  # Hex string like "#ff0000" or None

    @model_validator(mode="before")
    @classmethod
    def _from_api(cls, data: dict) -> dict:  # type: ignore[override]
        if "position" in data and isinstance(data.get("id"), Snowflake):
            return data

        rid = Snowflake.parse(str(data["id"]))
        name = data["name"]
        position = data["position"]

        color_int = data.get("color", 0)
        color = None
        if color_int and color_int > 0:
            color = f"#{color_int:06x}"

        return {
            "id": rid,
            "name": name,
            "position": position,
            "color": color,
        }
