"""CLI application - main entry point with all commands."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import click
from rich.console import Console

if TYPE_CHECKING:
    from discord_chat_exporter.core.discord.snowflake import Snowflake

console = Console()


class SnowflakeParamType(click.ParamType):
    """Click parameter type for Discord snowflake IDs."""

    name = "snowflake"

    def convert(self, value: str, param: click.Parameter | None, ctx: click.Context | None) -> Snowflake:
        from discord_chat_exporter.core.discord.snowflake import Snowflake

        result = Snowflake.try_parse(value)
        if result is None:
            self.fail(f"Invalid snowflake: {value!r}", param, ctx)
        return result


class ExportFormatParamType(click.ParamType):
    """Click parameter type for export format."""

    name = "format"

    def convert(self, value: str, param: click.Parameter | None, ctx: click.Context | None) -> str:
        from discord_chat_exporter.core.exporting.format import ExportFormat

        normalized = value.lower().replace("-", "").replace("_", "")
        for fmt in ExportFormat:
            if fmt.value == normalized:
                return fmt
            if fmt.name.lower().replace("_", "") == normalized:
                return fmt
        self.fail(
            f"Invalid format: {value!r}. Choose from: "
            + ", ".join(f.value for f in ExportFormat),
            param,
            ctx,
        )


SNOWFLAKE = SnowflakeParamType()
EXPORT_FORMAT = ExportFormatParamType()

# Common options
token_option = click.option(
    "-t", "--token", envvar="DISCORD_TOKEN", required=True, help="Discord token."
)


@click.group()
@click.version_option(package_name="discord-chat-exporter")
def cli() -> None:
    """Discord Chat Exporter - export Discord chat logs to a file."""


@cli.command()
@token_option
def guilds(token: str) -> None:
    """List accessible guilds."""

    async def _run() -> None:
        from discord_chat_exporter.core.discord.client import DiscordClient

        async with DiscordClient(token) as client:
            guild_list = await client.get_guilds()
            for g in guild_list:
                console.print(f"{g.id} | {g.name}")

    asyncio.run(_run())


@cli.command()
@token_option
@click.argument("guild_id", type=SNOWFLAKE)
def channels(token: str, guild_id: Snowflake) -> None:
    """List channels in a guild."""

    async def _run() -> None:
        from discord_chat_exporter.core.discord.client import DiscordClient

        async with DiscordClient(token) as client:
            channel_list = await client.get_channels(guild_id)
            for c in sorted(channel_list, key=lambda ch: ch.position or 0):
                console.print(f"{c.id} | {c.kind.name:<25} | {c.name}")

    asyncio.run(_run())


@cli.command("dm")
@token_option
def dm_channels(token: str) -> None:
    """List direct message channels."""

    async def _run() -> None:
        from discord_chat_exporter.core.discord.client import DiscordClient

        async with DiscordClient(token) as client:
            dm_list = await client.get_dm_channels()
            for c in dm_list:
                console.print(f"{c.id} | {c.name}")

    asyncio.run(_run())


@cli.command()
@token_option
@click.argument("channel_ids", type=SNOWFLAKE, nargs=-1, required=True)
@click.option("-o", "--output", default=None, help="Output file path template.")
@click.option(
    "-f",
    "--format",
    "export_format",
    type=EXPORT_FORMAT,
    default="htmldark",
    help="Export format.",
)
@click.option("--after", type=SNOWFLAKE, default=None, help="Only messages after this ID/date.")
@click.option("--before", type=SNOWFLAKE, default=None, help="Only messages before this ID/date.")
@click.option("--partition", default=None, help="Partition limit (e.g. '10' or '10mb').")
@click.option("--filter", "message_filter", default=None, help="Message filter expression.")
@click.option(
    "--media/--no-media",
    "download_media",
    default=False,
    help="Download referenced media.",
)
@click.option(
    "--threads",
    "thread_mode",
    type=click.Choice(["none", "active", "all"], case_sensitive=False),
    default="none",
    help="Include threads.",
)
@click.option(
    "--parallel",
    "parallel_limit",
    type=int,
    default=1,
    help="Number of parallel exports.",
)
def export(
    token: str,
    channel_ids: tuple[Snowflake, ...],
    output: str | None,
    export_format: str,
    after: Snowflake | None,
    before: Snowflake | None,
    partition: str | None,
    message_filter: str | None,
    download_media: bool,
    thread_mode: str,
    parallel_limit: int,
) -> None:
    """Export one or more channels."""

    async def _run() -> None:
        from discord_chat_exporter.core.discord.client import DiscordClient
        from discord_chat_exporter.core.exporting.channel_exporter import ChannelExporter
        from discord_chat_exporter.core.exporting.filtering.parser import parse_filter
        from discord_chat_exporter.core.exporting.partitioning import PartitionLimit
        from discord_chat_exporter.core.exporting.request import ExportRequest

        msg_filter = parse_filter(message_filter) if message_filter else None
        part_limit = PartitionLimit.parse(partition) if partition else PartitionLimit.null()

        async with DiscordClient(token) as client:
            semaphore = asyncio.Semaphore(parallel_limit)

            async def _export_channel(cid: Snowflake) -> None:
                async with semaphore:
                    channel = await client.get_channel(cid)
                    guild = await client.get_guild(channel.guild_id)

                    request = ExportRequest(
                        guild=guild,
                        channel=channel,
                        output_path=output or "",
                        export_format=export_format,
                        after=after,
                        before=before,
                        partition_limit=part_limit,
                        message_filter=msg_filter,
                        should_download_media=download_media,
                    )

                    exporter = ChannelExporter(client)
                    await exporter.export(request)
                    console.print(f"Exported: {channel.name}")

            tasks = [_export_channel(cid) for cid in channel_ids]
            await asyncio.gather(*tasks)

    asyncio.run(_run())


@cli.command("exportall")
@token_option
@click.argument("guild_id", type=SNOWFLAKE)
@click.option("-o", "--output", default=None, help="Output file path template.")
@click.option(
    "-f",
    "--format",
    "export_format",
    type=EXPORT_FORMAT,
    default="htmldark",
    help="Export format.",
)
@click.option("--after", type=SNOWFLAKE, default=None, help="Only messages after this ID/date.")
@click.option("--before", type=SNOWFLAKE, default=None, help="Only messages before this ID/date.")
@click.option("--partition", default=None, help="Partition limit (e.g. '10' or '10mb').")
@click.option("--filter", "message_filter", default=None, help="Message filter expression.")
@click.option(
    "--media/--no-media",
    "download_media",
    default=False,
    help="Download referenced media.",
)
@click.option(
    "--threads",
    "thread_mode",
    type=click.Choice(["none", "active", "all"], case_sensitive=False),
    default="none",
    help="Include threads.",
)
@click.option(
    "--parallel",
    "parallel_limit",
    type=int,
    default=1,
    help="Number of parallel exports.",
)
def export_all(
    token: str,
    guild_id: Snowflake,
    output: str | None,
    export_format: str,
    after: Snowflake | None,
    before: Snowflake | None,
    partition: str | None,
    message_filter: str | None,
    download_media: bool,
    thread_mode: str,
    parallel_limit: int,
) -> None:
    """Export all channels in a guild."""

    async def _run() -> None:
        from discord_chat_exporter.core.discord.client import DiscordClient
        from discord_chat_exporter.core.exporting.channel_exporter import ChannelExporter
        from discord_chat_exporter.core.exporting.filtering.parser import parse_filter
        from discord_chat_exporter.core.exporting.partitioning import PartitionLimit
        from discord_chat_exporter.core.exporting.request import ExportRequest

        msg_filter = parse_filter(message_filter) if message_filter else None
        part_limit = PartitionLimit.parse(partition) if partition else PartitionLimit.null()

        async with DiscordClient(token) as client:
            guild = await client.get_guild(guild_id)
            all_channels = await client.get_channels(guild_id)

            # Include threads if requested
            if thread_mode != "none":
                threads = await client.get_guild_threads(guild_id)
                if thread_mode == "active":
                    all_channels.extend(t for t in threads if not t.is_archived)
                else:
                    all_channels.extend(threads)

            # Filter to exportable channels
            exportable = [
                c
                for c in all_channels
                if not c.is_category and not c.is_empty
            ]

            console.print(f"Found {len(exportable)} channels to export in {guild.name}")

            semaphore = asyncio.Semaphore(parallel_limit)

            async def _export_channel(channel):  # type: ignore[no-untyped-def]
                async with semaphore:
                    request = ExportRequest(
                        guild=guild,
                        channel=channel,
                        output_path=output or "",
                        export_format=export_format,
                        after=after,
                        before=before,
                        partition_limit=part_limit,
                        message_filter=msg_filter,
                        should_download_media=download_media,
                    )

                    exporter = ChannelExporter(client)
                    await exporter.export(request)
                    console.print(f"Exported: {channel.name}")

            tasks = [_export_channel(c) for c in exportable]
            await asyncio.gather(*tasks)

    asyncio.run(_run())


@cli.command("exportdm")
@token_option
@click.option("-o", "--output", default=None, help="Output file path template.")
@click.option(
    "-f",
    "--format",
    "export_format",
    type=EXPORT_FORMAT,
    default="htmldark",
    help="Export format.",
)
@click.option("--after", type=SNOWFLAKE, default=None, help="Only messages after this ID/date.")
@click.option("--before", type=SNOWFLAKE, default=None, help="Only messages before this ID/date.")
@click.option("--partition", default=None, help="Partition limit (e.g. '10' or '10mb').")
@click.option("--filter", "message_filter", default=None, help="Message filter expression.")
@click.option(
    "--media/--no-media",
    "download_media",
    default=False,
    help="Download referenced media.",
)
@click.option(
    "--parallel",
    "parallel_limit",
    type=int,
    default=1,
    help="Number of parallel exports.",
)
def export_dm(
    token: str,
    output: str | None,
    export_format: str,
    after: Snowflake | None,
    before: Snowflake | None,
    partition: str | None,
    message_filter: str | None,
    download_media: bool,
    parallel_limit: int,
) -> None:
    """Export all direct message channels."""

    async def _run() -> None:
        from discord_chat_exporter.core.discord.client import DiscordClient
        from discord_chat_exporter.core.discord.models.guild import Guild
        from discord_chat_exporter.core.exporting.channel_exporter import ChannelExporter
        from discord_chat_exporter.core.exporting.filtering.parser import parse_filter
        from discord_chat_exporter.core.exporting.partitioning import PartitionLimit
        from discord_chat_exporter.core.exporting.request import ExportRequest

        msg_filter = parse_filter(message_filter) if message_filter else None
        part_limit = PartitionLimit.parse(partition) if partition else PartitionLimit.null()

        async with DiscordClient(token) as client:
            guild = Guild.DIRECT_MESSAGES
            dm_list = await client.get_dm_channels()
            exportable = [c for c in dm_list if not c.is_empty]

            console.print(f"Found {len(exportable)} DM channels to export")

            semaphore = asyncio.Semaphore(parallel_limit)

            async def _export_channel(channel):  # type: ignore[no-untyped-def]
                async with semaphore:
                    request = ExportRequest(
                        guild=guild,
                        channel=channel,
                        output_path=output or "",
                        export_format=export_format,
                        after=after,
                        before=before,
                        partition_limit=part_limit,
                        message_filter=msg_filter,
                        should_download_media=download_media,
                    )

                    exporter = ChannelExporter(client)
                    await exporter.export(request)
                    console.print(f"Exported: {channel.name}")

            tasks = [_export_channel(c) for c in exportable]
            await asyncio.gather(*tasks)

    asyncio.run(_run())
