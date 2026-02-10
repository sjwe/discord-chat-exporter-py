"""Integration tests for the export pipeline.

Exercises ChannelExporter → MessageExporter → Writers for all 4 formats.
"""

from __future__ import annotations

import csv
import io
import json
import os
from datetime import datetime, timezone

import pytest

from discord_chat_exporter.core.discord.models.channel import Channel, ChannelKind
from discord_chat_exporter.core.discord.models.message import Message, MessageKind
from discord_chat_exporter.core.discord.snowflake import Snowflake
from discord_chat_exporter.core.exceptions import ChannelEmptyError, DiscordChatExporterError
from discord_chat_exporter.core.exporting.channel_exporter import ChannelExporter
from discord_chat_exporter.core.exporting.filtering.filters import (
    FromMessageFilter,
    HasMessageFilter,
)
from discord_chat_exporter.core.exporting.format import ExportFormat
from discord_chat_exporter.core.exporting.partitioning import PartitionLimit
from discord_chat_exporter.core.exporting.request import ExportRequest
from tests.conftest import MockDiscordClient, export_to_format


# ===================================================================
# PlainText
# ===================================================================


class TestPlainTextExport:
    @pytest.mark.asyncio
    async def test_basic_export(self, tmp_path, mock_guild, mock_channel, mock_messages):
        content = await export_to_format(
            tmp_path, ExportFormat.PLAIN_TEXT, mock_guild, mock_channel, mock_messages
        )
        # Preamble should contain guild and channel info
        assert "Test Guild" in content
        assert "test-channel" in content
        # Should contain all message content
        assert "Hello, world!" in content
        assert "Check out this file" in content
        assert "React to this!" in content
        assert "This is a reply" in content
        # Postamble with exported count
        assert "Exported 5 message(s)" in content

    @pytest.mark.asyncio
    async def test_attachment_shown(self, tmp_path, mock_guild, mock_channel, mock_messages):
        content = await export_to_format(
            tmp_path, ExportFormat.PLAIN_TEXT, mock_guild, mock_channel, mock_messages
        )
        assert "image.png" in content

    @pytest.mark.asyncio
    async def test_reactions_shown(self, tmp_path, mock_guild, mock_channel, mock_messages):
        content = await export_to_format(
            tmp_path, ExportFormat.PLAIN_TEXT, mock_guild, mock_channel, mock_messages
        )
        # Reaction emoji and count
        assert "\U0001f44d" in content
        assert "(3)" in content

    @pytest.mark.asyncio
    async def test_utf8_encoding(self, tmp_path, mock_guild, mock_channel, mock_user):
        msg = Message(
            id=Snowflake(7001),
            kind=MessageKind.DEFAULT,
            author=mock_user,
            timestamp=datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
            content="Unicode test: \u00e9\u00e0\u00fc \u4f60\u597d \U0001f600",
        )
        output_path = os.path.join(str(tmp_path), "export.txt")
        client = MockDiscordClient(
            channels=[mock_channel], messages=[msg]
        )
        request = ExportRequest(
            guild=mock_guild,
            channel=mock_channel,
            output_path=output_path,
            export_format=ExportFormat.PLAIN_TEXT,
            is_utc_normalization_enabled=True,
        )
        exporter = ChannelExporter(client)
        await exporter.export(request)

        with open(request.output_file_path, encoding="utf-8") as f:
            content = f.read()
        assert "\u00e9\u00e0\u00fc" in content
        assert "\u4f60\u597d" in content
        assert "\U0001f600" in content


# ===================================================================
# CSV
# ===================================================================


class TestCsvExport:
    @pytest.mark.asyncio
    async def test_basic_export(self, tmp_path, mock_guild, mock_channel, mock_messages):
        content = await export_to_format(
            tmp_path, ExportFormat.CSV, mock_guild, mock_channel, mock_messages
        )
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        # Header + 5 messages
        assert len(rows) == 6
        assert rows[0] == ["AuthorID", "Author", "Date", "Content", "Attachments", "Reactions"]

    @pytest.mark.asyncio
    async def test_content_correctness(self, tmp_path, mock_guild, mock_channel, mock_messages):
        content = await export_to_format(
            tmp_path, ExportFormat.CSV, mock_guild, mock_channel, mock_messages
        )
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        # First data row (basic message)
        row = rows[1]
        assert row[0] == "1001"  # AuthorID
        assert row[1] == "testuser"  # Author
        assert row[3] == "Hello, world!"  # Content

    @pytest.mark.asyncio
    async def test_attachment_in_csv(self, tmp_path, mock_guild, mock_channel, mock_messages):
        content = await export_to_format(
            tmp_path, ExportFormat.CSV, mock_guild, mock_channel, mock_messages
        )
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        # Second data row has attachment
        attachment_col = rows[2][4]
        assert "image.png" in attachment_col

    @pytest.mark.asyncio
    async def test_reactions_in_csv(self, tmp_path, mock_guild, mock_channel, mock_messages):
        content = await export_to_format(
            tmp_path, ExportFormat.CSV, mock_guild, mock_channel, mock_messages
        )
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        # Third data row has reaction
        reaction_col = rows[3][5]
        assert "\U0001f44d" in reaction_col
        assert "(3)" in reaction_col


# ===================================================================
# JSON
# ===================================================================


class TestJsonExport:
    @pytest.mark.asyncio
    async def test_basic_export(self, tmp_path, mock_guild, mock_channel, mock_messages):
        content = await export_to_format(
            tmp_path, ExportFormat.JSON, mock_guild, mock_channel, mock_messages
        )
        data = json.loads(content)
        assert "guild" in data
        assert "channel" in data
        assert "messages" in data
        assert "messageCount" in data

    @pytest.mark.asyncio
    async def test_guild_info(self, tmp_path, mock_guild, mock_channel, mock_messages):
        content = await export_to_format(
            tmp_path, ExportFormat.JSON, mock_guild, mock_channel, mock_messages
        )
        data = json.loads(content)
        assert data["guild"]["id"] == "1"
        assert data["guild"]["name"] == "Test Guild"

    @pytest.mark.asyncio
    async def test_channel_info(self, tmp_path, mock_guild, mock_channel, mock_messages):
        content = await export_to_format(
            tmp_path, ExportFormat.JSON, mock_guild, mock_channel, mock_messages
        )
        data = json.loads(content)
        assert data["channel"]["id"] == "100"
        assert data["channel"]["name"] == "test-channel"
        assert data["channel"]["topic"] == "Test channel topic"

    @pytest.mark.asyncio
    async def test_message_content(self, tmp_path, mock_guild, mock_channel, mock_messages):
        content = await export_to_format(
            tmp_path, ExportFormat.JSON, mock_guild, mock_channel, mock_messages
        )
        data = json.loads(content)
        msgs = data["messages"]
        assert msgs[0]["content"] == "Hello, world!"
        assert msgs[0]["author"]["name"] == "testuser"

    @pytest.mark.asyncio
    async def test_attachment(self, tmp_path, mock_guild, mock_channel, mock_messages):
        content = await export_to_format(
            tmp_path, ExportFormat.JSON, mock_guild, mock_channel, mock_messages
        )
        data = json.loads(content)
        attachments = data["messages"][1]["attachments"]
        assert len(attachments) == 1
        assert attachments[0]["fileName"] == "image.png"
        assert "image.png" in attachments[0]["url"]

    @pytest.mark.asyncio
    async def test_reactions(self, tmp_path, mock_guild, mock_channel, mock_messages):
        content = await export_to_format(
            tmp_path, ExportFormat.JSON, mock_guild, mock_channel, mock_messages
        )
        data = json.loads(content)
        reactions = data["messages"][2]["reactions"]
        assert len(reactions) == 1
        assert reactions[0]["count"] == 3

    @pytest.mark.asyncio
    async def test_message_count(self, tmp_path, mock_guild, mock_channel, mock_messages):
        content = await export_to_format(
            tmp_path, ExportFormat.JSON, mock_guild, mock_channel, mock_messages
        )
        data = json.loads(content)
        assert data["messageCount"] == 5
        assert len(data["messages"]) == 5


# ===================================================================
# HTML Dark
# ===================================================================


class TestHtmlDarkExport:
    @pytest.mark.asyncio
    async def test_basic_export(self, tmp_path, mock_guild, mock_channel, mock_messages):
        content = await export_to_format(
            tmp_path, ExportFormat.HTML_DARK, mock_guild, mock_channel, mock_messages
        )
        assert "<!DOCTYPE html>" in content or "<html" in content

    @pytest.mark.asyncio
    async def test_theme_applied(self, tmp_path, mock_guild, mock_channel, mock_messages):
        content = await export_to_format(
            tmp_path, ExportFormat.HTML_DARK, mock_guild, mock_channel, mock_messages
        )
        # Dark theme uses dark background colors
        assert "#36393e" in content or "#2f3136" in content or "dark" in content.lower()

    @pytest.mark.asyncio
    async def test_content_present(self, tmp_path, mock_guild, mock_channel, mock_messages):
        content = await export_to_format(
            tmp_path, ExportFormat.HTML_DARK, mock_guild, mock_channel, mock_messages
        )
        assert "Hello, world!" in content
        assert "Check out this file" in content

    @pytest.mark.asyncio
    async def test_author_present(self, tmp_path, mock_guild, mock_channel, mock_messages):
        content = await export_to_format(
            tmp_path, ExportFormat.HTML_DARK, mock_guild, mock_channel, mock_messages
        )
        # Author names should appear in the HTML output
        assert "Test User" in content or "testuser" in content


# ===================================================================
# HTML Light
# ===================================================================


class TestHtmlLightExport:
    @pytest.mark.asyncio
    async def test_basic_export(self, tmp_path, mock_guild, mock_channel, mock_messages):
        content = await export_to_format(
            tmp_path, ExportFormat.HTML_LIGHT, mock_guild, mock_channel, mock_messages
        )
        assert "<!DOCTYPE html>" in content or "<html" in content

    @pytest.mark.asyncio
    async def test_theme_applied(self, tmp_path, mock_guild, mock_channel, mock_messages):
        content = await export_to_format(
            tmp_path, ExportFormat.HTML_LIGHT, mock_guild, mock_channel, mock_messages
        )
        # Light theme uses white/light background colors
        assert "#ffffff" in content or "#f2f3f5" in content or "light" in content.lower()


# ===================================================================
# Partition rotation
# ===================================================================


class TestPartitionRotation:
    @pytest.mark.asyncio
    async def test_message_count_partition(
        self, tmp_path, mock_guild, mock_channel, mock_messages
    ):
        """Partition every 2 messages should produce 3 files (2+2+1)."""
        output_path = os.path.join(str(tmp_path), "export.txt")
        partition_limit = PartitionLimit.parse("2")

        client = MockDiscordClient(
            channels=[mock_channel], messages=mock_messages
        )
        request = ExportRequest(
            guild=mock_guild,
            channel=mock_channel,
            output_path=output_path,
            export_format=ExportFormat.PLAIN_TEXT,
            partition_limit=partition_limit,
            is_utc_normalization_enabled=True,
        )

        exporter = ChannelExporter(client)
        await exporter.export(request)

        # First file: export.txt
        assert os.path.exists(request.output_file_path)
        # Second file: export [part 2].txt
        part2 = os.path.join(str(tmp_path), "export [part 2].txt")
        assert os.path.exists(part2)
        # Third file: export [part 3].txt
        part3 = os.path.join(str(tmp_path), "export [part 3].txt")
        assert os.path.exists(part3)

    @pytest.mark.asyncio
    async def test_file_naming(self, tmp_path, mock_guild, mock_channel, mock_messages):
        """Partitioned files follow the [part N] naming convention."""
        output_path = os.path.join(str(tmp_path), "output.json")
        partition_limit = PartitionLimit.parse("3")

        client = MockDiscordClient(
            channels=[mock_channel], messages=mock_messages
        )
        request = ExportRequest(
            guild=mock_guild,
            channel=mock_channel,
            output_path=output_path,
            export_format=ExportFormat.JSON,
            partition_limit=partition_limit,
            is_utc_normalization_enabled=True,
        )

        exporter = ChannelExporter(client)
        await exporter.export(request)

        assert os.path.exists(os.path.join(str(tmp_path), "output.json"))
        assert os.path.exists(os.path.join(str(tmp_path), "output [part 2].json"))

        # Each partition should be valid JSON
        with open(os.path.join(str(tmp_path), "output.json"), encoding="utf-8") as f:
            data1 = json.loads(f.read())
        with open(os.path.join(str(tmp_path), "output [part 2].json"), encoding="utf-8") as f:
            data2 = json.loads(f.read())

        total = data1["messageCount"] + data2["messageCount"]
        assert total == 5


# ===================================================================
# Message filtering
# ===================================================================


class TestMessageFiltering:
    @pytest.mark.asyncio
    async def test_filter_from_user(
        self, tmp_path, mock_guild, mock_channel, mock_messages
    ):
        """from:testuser filter should only include messages from that user."""
        content = await export_to_format(
            tmp_path,
            ExportFormat.JSON,
            mock_guild,
            mock_channel,
            mock_messages,
            message_filter=FromMessageFilter("testuser"),
        )
        data = json.loads(content)
        # testuser authored messages 5001, 5003 (basic + reaction)
        for msg in data["messages"]:
            assert msg["author"]["name"] == "testuser"
        assert data["messageCount"] == 2

    @pytest.mark.asyncio
    async def test_filter_has_image(
        self, tmp_path, mock_guild, mock_channel, mock_messages
    ):
        """has:image filter should only include messages with image attachments."""
        content = await export_to_format(
            tmp_path,
            ExportFormat.JSON,
            mock_guild,
            mock_channel,
            mock_messages,
            message_filter=HasMessageFilter("image"),
        )
        data = json.loads(content)
        assert data["messageCount"] == 1
        assert len(data["messages"][0]["attachments"]) == 1


# ===================================================================
# Empty channel
# ===================================================================


class TestEmptyChannel:
    @pytest.mark.asyncio
    async def test_empty_channel_raises(self, tmp_path, mock_guild):
        """An empty channel should raise ChannelEmptyError."""
        empty_channel = Channel(
            id=Snowflake(200),
            kind=ChannelKind.GUILD_TEXT_CHAT,
            guild_id=Snowflake(1),
            name="empty-channel",
            last_message_id=None,
        )
        output_path = os.path.join(str(tmp_path), "export.txt")
        client = MockDiscordClient(channels=[empty_channel], messages=[])
        request = ExportRequest(
            guild=mock_guild,
            channel=empty_channel,
            output_path=output_path,
            export_format=ExportFormat.PLAIN_TEXT,
            is_utc_normalization_enabled=True,
        )

        exporter = ChannelExporter(client)
        with pytest.raises(ChannelEmptyError):
            await exporter.export(request)

        # Even on error, an empty file should be created (exporter.close() runs in finally)
        assert os.path.exists(request.output_file_path)


# ===================================================================
# Forum channel
# ===================================================================


class TestForumChannel:
    @pytest.mark.asyncio
    async def test_forum_channel_rejected(self, tmp_path, mock_guild):
        """Forum channels should be rejected with DiscordChatExporterError."""
        forum_channel = Channel(
            id=Snowflake(300),
            kind=ChannelKind.GUILD_FORUM,
            guild_id=Snowflake(1),
            name="forum-channel",
            last_message_id=Snowflake(999),
        )
        output_path = os.path.join(str(tmp_path), "export.txt")
        client = MockDiscordClient(channels=[forum_channel], messages=[])
        request = ExportRequest(
            guild=mock_guild,
            channel=forum_channel,
            output_path=output_path,
            export_format=ExportFormat.PLAIN_TEXT,
            is_utc_normalization_enabled=True,
        )

        exporter = ChannelExporter(client)
        with pytest.raises(DiscordChatExporterError, match="forum"):
            await exporter.export(request)
