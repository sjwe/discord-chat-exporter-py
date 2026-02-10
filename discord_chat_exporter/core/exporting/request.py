"""Export request configuration."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from discord_chat_exporter.core.discord.models.channel import Channel
    from discord_chat_exporter.core.discord.models.guild import Guild
    from discord_chat_exporter.core.discord.snowflake import Snowflake
    from discord_chat_exporter.core.exporting.filtering.base import MessageFilter
    from discord_chat_exporter.core.exporting.format import ExportFormat
    from discord_chat_exporter.core.exporting.partitioning import PartitionLimit


def _escape_filename(name: str) -> str:
    """Remove characters not allowed in file names."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)


def _format_path(
    path: str,
    guild: Guild,
    channel: Channel,
    after: Snowflake | None,
    before: Snowflake | None,
) -> str:
    """Replace %X placeholders in a path template."""

    def _replace(m: re.Match[str]) -> str:
        token = m.group(0)
        mapping: dict[str, str] = {
            "%g": str(guild.id),
            "%G": guild.name,
            "%t": str(channel.parent.id) if channel.parent else "",
            "%T": channel.parent.name if channel.parent else "",
            "%c": str(channel.id),
            "%C": channel.name,
            "%p": str(channel.position or 0),
            "%P": str(channel.parent.position or 0) if channel.parent else "0",
            "%a": after.to_date().strftime("%Y-%m-%d") if after else "",
            "%b": before.to_date().strftime("%Y-%m-%d") if before else "",
            "%d": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "%%": "%",
        }
        return _escape_filename(mapping.get(token, token))

    return re.sub(r"%.", _replace, path)


class ExportRequest:
    """Holds all parameters for a single channel export."""

    def __init__(
        self,
        guild: Guild,
        channel: Channel,
        output_path: str,
        export_format: ExportFormat,
        after: Snowflake | None = None,
        before: Snowflake | None = None,
        partition_limit: PartitionLimit | None = None,
        message_filter: MessageFilter | None = None,
        should_format_markdown: bool = True,
        should_download_media: bool = False,
        should_reuse_media: bool = True,
        assets_dir_path: str | None = None,
        locale: str | None = None,
        is_utc_normalization_enabled: bool = False,
    ) -> None:
        from discord_chat_exporter.core.exporting.filtering.base import NullMessageFilter
        from discord_chat_exporter.core.exporting.partitioning import PartitionLimit as PL

        self.guild = guild
        self.channel = channel
        self.export_format = export_format
        self.after = after
        self.before = before
        self.partition_limit = partition_limit or PL.null()
        self.message_filter = message_filter or NullMessageFilter()
        self.should_format_markdown = should_format_markdown
        self.should_download_media = should_download_media
        self.should_reuse_media = should_reuse_media
        self.locale = locale
        self.is_utc_normalization_enabled = is_utc_normalization_enabled

        self.output_file_path = self._get_output_base_file_path(
            guild, channel, output_path, export_format, after, before
        )
        self.output_dir_path = str(Path(self.output_file_path).parent)

        if assets_dir_path:
            self.assets_dir_path = _format_path(assets_dir_path, guild, channel, after, before)
        else:
            self.assets_dir_path = self.output_file_path + "_Files" + os.sep

    @staticmethod
    def get_default_output_filename(
        guild: Guild,
        channel: Channel,
        export_format: ExportFormat,
        after: Snowflake | None = None,
        before: Snowflake | None = None,
    ) -> str:
        parts: list[str] = [guild.name]

        if channel.parent is not None:
            parts.append(f" - {channel.parent.name}")

        parts.append(f" - {channel.name} [{channel.id}]")

        if after is not None or before is not None:
            if after and before:
                date_range = (
                    f"{after.to_date():%Y-%m-%d} to {before.to_date():%Y-%m-%d}"
                )
            elif after:
                date_range = f"after {after.to_date():%Y-%m-%d}"
            else:
                date_range = f"before {before.to_date():%Y-%m-%d}"  # type: ignore[union-attr]
            parts.append(f" ({date_range})")

        parts.append(f".{export_format.file_extension}")
        return _escape_filename("".join(parts))

    @classmethod
    def _get_output_base_file_path(
        cls,
        guild: Guild,
        channel: Channel,
        output_path: str,
        export_format: ExportFormat,
        after: Snowflake | None = None,
        before: Snowflake | None = None,
    ) -> str:
        actual_path = _format_path(output_path, guild, channel, after, before)

        # If output is a directory or has no extension, put default filename inside
        if os.path.isdir(actual_path) or not os.path.splitext(actual_path)[1]:
            filename = cls.get_default_output_filename(
                guild, channel, export_format, after, before
            )
            return os.path.join(actual_path, filename)

        return actual_path
