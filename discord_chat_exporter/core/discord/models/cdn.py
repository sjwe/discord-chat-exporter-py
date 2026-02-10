"""Discord CDN URL helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from discord_chat_exporter.core.discord.snowflake import Snowflake


class ImageCdn:
    """Static helper for building Discord CDN image URLs."""

    @staticmethod
    def get_standard_emoji_url(emoji_name: str) -> str:
        """Get Twemoji SVG URL for a standard Unicode emoji."""
        # Get all codepoints (Python 3 strings are already proper unicode, no surrogates)
        codepoints = [ord(c) for c in emoji_name]

        # Variant selector (0xfe0f) is skipped unless ZWJ (0x200d) is present
        has_zwj = 0x200D in codepoints
        if has_zwj:
            filtered = codepoints
        else:
            filtered = [cp for cp in codepoints if cp != 0xFE0F]

        twemoji_id = "-".join(f"{cp:x}" for cp in filtered)
        return f"https://cdn.jsdelivr.net/gh/twitter/twemoji@latest/assets/svg/{twemoji_id}.svg"

    @staticmethod
    def get_custom_emoji_url(emoji_id: Snowflake, is_animated: bool = False) -> str:
        ext = "gif" if is_animated else "png"
        return f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}"

    @staticmethod
    def get_guild_icon_url(guild_id: Snowflake, icon_hash: str, size: int = 512) -> str:
        ext = "gif" if icon_hash.startswith("a_") else "png"
        return f"https://cdn.discordapp.com/icons/{guild_id}/{icon_hash}.{ext}?size={size}"

    @staticmethod
    def get_channel_icon_url(channel_id: Snowflake, icon_hash: str, size: int = 512) -> str:
        ext = "gif" if icon_hash.startswith("a_") else "png"
        return (
            f"https://cdn.discordapp.com/channel-icons/{channel_id}/{icon_hash}.{ext}?size={size}"
        )

    @staticmethod
    def get_user_avatar_url(user_id: Snowflake, avatar_hash: str, size: int = 512) -> str:
        ext = "gif" if avatar_hash.startswith("a_") else "png"
        return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{ext}?size={size}"

    @staticmethod
    def get_fallback_user_avatar_url(index: int = 0) -> str:
        return f"https://cdn.discordapp.com/embed/avatars/{index}.png"

    @staticmethod
    def get_member_avatar_url(
        guild_id: Snowflake,
        user_id: Snowflake,
        avatar_hash: str,
        size: int = 512,
    ) -> str:
        ext = "gif" if avatar_hash.startswith("a_") else "png"
        return (
            f"https://cdn.discordapp.com/guilds/{guild_id}/users/{user_id}"
            f"/avatars/{avatar_hash}.{ext}?size={size}"
        )

    @staticmethod
    def get_sticker_url(sticker_id: Snowflake, fmt: str = "png") -> str:
        return f"https://cdn.discordapp.com/stickers/{sticker_id}.{fmt}"
