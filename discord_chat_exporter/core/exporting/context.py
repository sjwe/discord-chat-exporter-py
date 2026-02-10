"""Export context - caches members, channels, roles and resolves assets."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from urllib.parse import quote

from discord_chat_exporter.core.discord.models.member import Member
from discord_chat_exporter.core.discord.models.message import MessageKind
from discord_chat_exporter.core.discord.snowflake import Snowflake
from discord_chat_exporter.core.exporting.format import ExportFormat

if TYPE_CHECKING:
    from discord_chat_exporter.core.discord.client import DiscordClient
    from discord_chat_exporter.core.discord.models.channel import Channel
    from discord_chat_exporter.core.discord.models.message import Message
    from discord_chat_exporter.core.discord.models.role import Role
    from discord_chat_exporter.core.discord.models.user import User
    from discord_chat_exporter.core.exporting.asset_downloader import ExportAssetDownloader
    from discord_chat_exporter.core.exporting.request import ExportRequest


class ExportContext:
    """Holds caches and provides lookups during export."""

    def __init__(self, discord: DiscordClient, request: ExportRequest) -> None:
        self.discord = discord
        self.request = request
        self._members: dict[Snowflake, Member | None] = {}
        self._channels: dict[Snowflake, Channel] = {}
        self._roles: dict[Snowflake, Role] = {}
        self._downloader: ExportAssetDownloader | None = None

    # -- date formatting --

    def normalize_date(self, instant: datetime) -> datetime:
        if self.request.is_utc_normalization_enabled:
            return instant.astimezone(timezone.utc)
        return instant.astimezone()

    def format_date(self, instant: datetime, fmt: str = "g") -> str:
        """Format a datetime using Discord-style format codes.

        Codes: t (short time), T (long time), d (short date), D (long date),
        f (long date + short time), F (long date + day + short time),
        g (short date + short time, default).
        Falls back to strftime for unrecognized codes.
        """
        dt = self.normalize_date(instant)
        discord_formats: dict[str, str] = {
            "t": "%H:%M",
            "T": "%H:%M:%S",
            "d": "%m/%d/%Y",
            "D": "%B %d, %Y",
            "f": "%B %d, %Y %H:%M",
            "F": "%A, %B %d, %Y %H:%M",
            "g": "%m/%d/%Y %H:%M",
        }
        strftime_fmt = discord_formats.get(fmt, fmt)
        return dt.strftime(strftime_fmt)

    # -- populate caches --

    async def populate_channels_and_roles(self) -> None:
        channels = await self.discord.get_channels(self.request.guild.id)
        for ch in channels:
            self._channels[ch.id] = ch

        roles = await self.discord.get_roles(self.request.guild.id)
        for role in roles:
            self._roles[role.id] = role

    async def populate_member(self, user: User) -> None:
        await self._populate_member(user.id, user)

    async def populate_member_by_id(self, member_id: Snowflake) -> None:
        await self._populate_member(member_id, None)

    async def _populate_member(
        self, member_id: Snowflake, fallback_user: User | None
    ) -> None:
        if member_id in self._members:
            return

        member = await self.discord.try_get_member(self.request.guild.id, member_id)

        if member is None and fallback_user is not None:
            member = Member.create_fallback(fallback_user)

        # Store even if None to avoid re-fetching
        self._members[member_id] = member

    # -- lookups --

    def try_get_member(self, member_id: Snowflake) -> Member | None:
        return self._members.get(member_id)

    def try_get_channel(self, channel_id: Snowflake) -> Channel | None:
        return self._channels.get(channel_id)

    def try_get_role(self, role_id: Snowflake) -> Role | None:
        return self._roles.get(role_id)

    def get_user_roles(self, user_id: Snowflake) -> list[Role]:
        member = self.try_get_member(user_id)
        if not member:
            return []
        roles = [self.try_get_role(rid) for rid in member.role_ids]
        return sorted(
            [r for r in roles if r is not None],
            key=lambda r: r.position,
            reverse=True,
        )

    def try_get_user_color(self, user_id: Snowflake) -> str | None:
        for role in self.get_user_roles(user_id):
            if role.color:
                return role.color
        return None

    # -- asset resolution --

    def _get_downloader(self):
        """Get or create the shared asset downloader instance."""
        if self._downloader is None:
            from discord_chat_exporter.core.exporting.asset_downloader import ExportAssetDownloader

            self._downloader = ExportAssetDownloader(
                self.request.assets_dir_path,
                self.request.should_reuse_media,
            )
        return self._downloader

    async def resolve_asset_url(self, url: str) -> str:
        if not self.request.should_download_media:
            return url

        try:
            downloader = self._get_downloader()
            file_path = await downloader.download(url)

            # If download was skipped (disallowed domain), the URL is returned as-is
            if file_path == url:
                return url

            rel_path = os.path.relpath(file_path, self.request.output_dir_path)

            if rel_path.startswith(".."):
                optimal_path = file_path
            else:
                optimal_path = rel_path

            if self.request.export_format.is_html:
                return quote(optimal_path, safe="/\\:")

            return optimal_path
        except Exception:
            return url

    async def close(self) -> None:
        """Clean up resources."""
        if self._downloader is not None and hasattr(self._downloader, 'close'):
            await self._downloader.close()
            self._downloader = None

    # -- message helpers --

    @staticmethod
    def get_fallback_content(message: Message) -> str:
        """Get system notification fallback text."""
        kind = message.kind
        if kind == MessageKind.RECIPIENT_ADD:
            if message.mentioned_users:
                return f"Added {message.mentioned_users[0].display_name} to the group."
            return "Added a recipient."
        if kind == MessageKind.RECIPIENT_REMOVE:
            if message.mentioned_users:
                if message.author.id == message.mentioned_users[0].id:
                    return "Left the group."
                return f"Removed {message.mentioned_users[0].display_name} from the group."
            return "Removed a recipient."
        if kind == MessageKind.CALL:
            if message.call_ended_timestamp:
                delta = message.call_ended_timestamp - message.timestamp
                minutes = delta.total_seconds() / 60
                return f"Started a call that lasted {minutes:,.0f} minutes."
            return "Started a call that lasted 0 minutes."
        if kind == MessageKind.CHANNEL_NAME_CHANGE:
            if message.content.strip():
                return f"Changed the channel name: {message.content}"
            return "Changed the channel name."
        if kind == MessageKind.CHANNEL_ICON_CHANGE:
            return "Changed the channel icon."
        if kind == MessageKind.CHANNEL_PINNED_MESSAGE:
            return "Pinned a message."
        if kind == MessageKind.THREAD_CREATED:
            return "Started a thread."
        if kind == MessageKind.GUILD_MEMBER_JOIN:
            return "Joined the server."
        return message.content
