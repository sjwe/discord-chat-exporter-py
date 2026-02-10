"""Embed model and related types."""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, model_validator

from discord_chat_exporter.core.discord.snowflake import Snowflake


class EmbedKind(Enum):
    RICH = "rich"
    IMAGE = "image"
    VIDEO = "video"
    GIFV = "gifv"
    LINK = "link"


class EmbedAuthor(BaseModel):
    model_config = {"frozen": True}

    name: str | None = None
    url: str | None = None
    icon_url: str | None = None
    icon_proxy_url: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _from_api(cls, data: dict) -> dict:  # type: ignore[override]
        if "icon_proxy_url" in data or "icon_url" in data:
            return data
        return {
            "name": data.get("name"),
            "url": data.get("url"),
            "icon_url": data.get("icon_url"),
            "icon_proxy_url": data.get("proxy_icon_url"),
        }


class EmbedField(BaseModel):
    model_config = {"frozen": True}

    name: str
    value: str
    is_inline: bool = False

    @model_validator(mode="before")
    @classmethod
    def _from_api(cls, data: dict) -> dict:  # type: ignore[override]
        if "is_inline" in data:
            return data
        return {
            "name": data["name"],
            "value": data["value"],
            "is_inline": data.get("inline", False),
        }


class EmbedImage(BaseModel):
    model_config = {"frozen": True}

    url: str | None = None
    proxy_url: str | None = None
    width: int | None = None
    height: int | None = None


class EmbedVideo(BaseModel):
    model_config = {"frozen": True}

    url: str | None = None
    proxy_url: str | None = None
    width: int | None = None
    height: int | None = None


class EmbedFooter(BaseModel):
    model_config = {"frozen": True}

    text: str
    icon_url: str | None = None
    icon_proxy_url: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _from_api(cls, data: dict) -> dict:  # type: ignore[override]
        if "icon_proxy_url" in data:
            return data
        return {
            "text": data["text"],
            "icon_url": data.get("icon_url"),
            "icon_proxy_url": data.get("proxy_icon_url"),
        }


class Embed(BaseModel):
    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    title: str | None = None
    kind: EmbedKind = EmbedKind.RICH
    url: str | None = None
    timestamp: datetime | None = None
    color: str | None = None  # Hex string like "#rrggbb"
    author: EmbedAuthor | None = None
    description: str | None = None
    fields: list[EmbedField] = []
    thumbnail: EmbedImage | None = None
    images: list[EmbedImage] = []
    video: EmbedVideo | None = None
    footer: EmbedFooter | None = None

    @property
    def image(self) -> EmbedImage | None:
        return self.images[0] if self.images else None

    def try_get_spotify_track(self) -> SpotifyTrackEmbedProjection | None:
        return SpotifyTrackEmbedProjection.try_resolve(self)

    def try_get_twitch_clip(self) -> TwitchClipEmbedProjection | None:
        return TwitchClipEmbedProjection.try_resolve(self)

    def try_get_youtube_video(self) -> YouTubeVideoEmbedProjection | None:
        return YouTubeVideoEmbedProjection.try_resolve(self)

    @model_validator(mode="before")
    @classmethod
    def _from_api(cls, data: dict) -> dict:  # type: ignore[override]
        if isinstance(data.get("kind"), EmbedKind):
            return data

        kind_str = data.get("type", "rich")
        try:
            kind = EmbedKind(kind_str.lower())
        except ValueError:
            kind = EmbedKind.RICH

        color_int = data.get("color")
        color = f"#{color_int & 0xFFFFFF:06x}" if color_int else None

        author = data.get("author")
        if author and isinstance(author, dict):
            author = EmbedAuthor.model_validate(author)

        fields = [
            EmbedField.model_validate(f) if isinstance(f, dict) else f
            for f in data.get("fields", [])
        ]

        thumbnail = data.get("thumbnail")
        if thumbnail and isinstance(thumbnail, dict):
            thumbnail = EmbedImage.model_validate(thumbnail)

        image_data = data.get("image")
        images = [EmbedImage.model_validate(image_data)] if image_data and isinstance(image_data, dict) else data.get("images", [])

        video = data.get("video")
        if video and isinstance(video, dict):
            video = EmbedVideo.model_validate(video)

        footer = data.get("footer")
        if footer and isinstance(footer, dict):
            footer = EmbedFooter.model_validate(footer)

        return {
            "title": data.get("title"),
            "kind": kind,
            "url": data.get("url"),
            "timestamp": data.get("timestamp"),
            "color": color,
            "author": author,
            "description": data.get("description"),
            "fields": fields,
            "thumbnail": thumbnail,
            "images": images,
            "video": video,
            "footer": footer,
        }


class SpotifyTrackEmbedProjection(BaseModel):
    track_id: str

    @property
    def url(self) -> str:
        return f"https://open.spotify.com/embed/track/{self.track_id}"

    @classmethod
    def try_resolve(cls, embed: Embed) -> SpotifyTrackEmbedProjection | None:
        if embed.kind != EmbedKind.LINK or not embed.url:
            return None
        m = re.search(r"spotify\.com/track/(.*?)(?:\?|&|/|$)", embed.url)
        if not m or not m.group(1):
            return None
        return cls(track_id=m.group(1))


class YouTubeVideoEmbedProjection(BaseModel):
    video_id: str

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/embed/{self.video_id}"

    @classmethod
    def try_resolve(cls, embed: Embed) -> YouTubeVideoEmbedProjection | None:
        if embed.kind != EmbedKind.VIDEO or not embed.url:
            return None
        # Match common YouTube URL patterns
        patterns = [
            r"youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",
            r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
            r"youtu\.be/([a-zA-Z0-9_-]{11})",
            r"youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
        ]
        for pattern in patterns:
            m = re.search(pattern, embed.url)
            if m:
                return cls(video_id=m.group(1))
        return None


class TwitchClipEmbedProjection(BaseModel):
    clip_id: str

    @property
    def url(self) -> str:
        return f"https://clips.twitch.tv/embed?clip={self.clip_id}&parent=localhost"

    @classmethod
    def try_resolve(cls, embed: Embed) -> TwitchClipEmbedProjection | None:
        if embed.kind != EmbedKind.VIDEO or not embed.url:
            return None
        for pattern in [
            r"clips\.twitch\.tv/(.*?)(?:\?|&|/|$)",
            r"twitch\.tv/clip/(.*?)(?:\?|&|/|$)",
        ]:
            m = re.search(pattern, embed.url)
            if m and m.group(1):
                return cls(clip_id=m.group(1))
        return None
