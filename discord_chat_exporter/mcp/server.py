"""MCP server exposing Discord chat export tools for LLM consumption."""

from __future__ import annotations

import io
import os

from fastmcp import FastMCP

from discord_chat_exporter.core.discord.client import DiscordClient
from discord_chat_exporter.core.discord.models.guild import Guild
from discord_chat_exporter.core.discord.snowflake import Snowflake
from discord_chat_exporter.core.exporting.context import ExportContext
from discord_chat_exporter.core.exporting.filtering.parser import parse_filter
from discord_chat_exporter.core.exporting.format import ExportFormat
from discord_chat_exporter.core.exporting.request import ExportRequest
from discord_chat_exporter.core.exporting.writers.base import MessageWriter
from discord_chat_exporter.core.exporting.writers.csv import CsvMessageWriter
from discord_chat_exporter.core.exporting.writers.json import JsonMessageWriter
from discord_chat_exporter.core.exporting.writers.plaintext import PlainTextMessageWriter

mcp = FastMCP(name="discord-chat-exporter")

_discord_client: DiscordClient | None = None


async def _get_discord_client() -> DiscordClient:
    global _discord_client
    if _discord_client is None:
        token = os.environ.get("DISCORD_TOKEN")
        if not token:
            raise ValueError("DISCORD_TOKEN environment variable is required")
        _discord_client = DiscordClient(token)
    return _discord_client


_FORMAT_MAP = {
    "plaintext": ExportFormat.PLAIN_TEXT,
    "json": ExportFormat.JSON,
    "csv": ExportFormat.CSV,
}


def _make_writer(
    fmt: ExportFormat, stream: io.BytesIO, context: ExportContext
) -> MessageWriter:
    if fmt == ExportFormat.JSON:
        return JsonMessageWriter(stream, context)
    if fmt == ExportFormat.CSV:
        return CsvMessageWriter(stream, context)
    return PlainTextMessageWriter(stream, context)


@mcp.tool
async def list_guilds() -> list[dict]:
    """List all Discord guilds (servers) accessible with the configured token."""
    client = await _get_discord_client()
    guilds = await client.get_guilds()
    return [{"id": str(g.id), "name": g.name} for g in guilds]


@mcp.tool
async def list_channels(guild_id: str) -> list[dict]:
    """List all channels in a guild. Pass a guild ID from list_guilds."""
    client = await _get_discord_client()
    sid = Snowflake.parse(guild_id)
    channels = await client.get_channels(sid)
    return [
        {
            "id": str(ch.id),
            "name": ch.name,
            "kind": ch.kind.name,
            "topic": ch.topic,
            "parent_id": str(ch.parent.id) if ch.parent else None,
            "parent_name": ch.parent.name if ch.parent else None,
        }
        for ch in channels
    ]


@mcp.tool
async def list_dm_channels() -> list[dict]:
    """List all DM channels."""
    client = await _get_discord_client()
    channels = await client.get_dm_channels()
    return [{"id": str(ch.id), "name": ch.name} for ch in channels]


@mcp.tool
async def get_messages(
    channel_id: str,
    format: str = "plaintext",
    after: str | None = None,
    before: str | None = None,
    filter: str | None = None,
    max_words: int = 4000,
) -> str:
    """Retrieve messages from a channel, formatted inline.

    Args:
        channel_id: Discord channel ID.
        format: Output format — "plaintext", "json", or "csv".
        after: Only messages after this ISO date or snowflake ID.
        before: Only messages before this ISO date or snowflake ID.
        filter: Filter DSL expression, e.g. "from:user has:image".
        max_words: Approximate word cap on the response (default 4000).
    """
    client = await _get_discord_client()

    export_format = _FORMAT_MAP.get(format)
    if export_format is None:
        raise ValueError(f"Unsupported format {format!r}. Use: plaintext, json, csv")

    channel = await client.get_channel(Snowflake.parse(channel_id))

    if channel.guild_id and channel.guild_id != Snowflake.ZERO:
        guild = await client.get_guild(channel.guild_id)
    else:
        guild = Guild.DIRECT_MESSAGES

    after_sf = Snowflake.try_parse(after) if after else None
    before_sf = Snowflake.try_parse(before) if before else None

    message_filter = parse_filter(filter) if filter else None

    request = ExportRequest(
        guild=guild,
        channel=channel,
        output_path="/dev/null",
        export_format=export_format,
        after=after_sf,
        before=before_sf,
        message_filter=message_filter,
        should_format_markdown=True,
        should_download_media=False,
        is_utc_normalization_enabled=True,
    )

    context = ExportContext(client, request)
    await context.populate_channels_and_roles()

    buf = io.BytesIO()
    writer = _make_writer(export_format, buf, context)

    truncated = False
    try:
        await writer.write_preamble()

        async for message in client.get_messages(
            Snowflake.parse(channel_id), after=after_sf, before=before_sf
        ):
            await context.populate_member(message.author)

            if message_filter and not message_filter.is_match(message):
                continue

            await writer.write_message(message)

            word_count = len(buf.getvalue().decode("utf-8", errors="replace").split())
            if word_count >= max_words:
                truncated = True
                break

        await writer.write_postamble()
    finally:
        await context.close()

    result = buf.getvalue().decode("utf-8", errors="replace")

    if truncated:
        if export_format == ExportFormat.JSON:
            # Insert truncated field before the closing brace
            result = result.rstrip()
            if result.endswith("}"):
                result = result[:-1] + ',\n  "truncated": true\n}\n'
        else:
            word_count = len(result.split())
            result += (
                f"\n[Truncated at ~{word_count} words. Use 'after' parameter "
                "with last message timestamp to continue.]"
            )

    return result
