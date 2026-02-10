"""Tests for HtmlMarkdownVisitor and PlainTextMarkdownVisitor."""

from __future__ import annotations

from datetime import timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from discord_chat_exporter.core.discord.models.channel import Channel, ChannelKind
from discord_chat_exporter.core.discord.models.member import Member
from discord_chat_exporter.core.discord.models.role import Role
from discord_chat_exporter.core.discord.models.user import User
from discord_chat_exporter.core.discord.snowflake import Snowflake
from discord_chat_exporter.core.exporting.format import ExportFormat
from discord_chat_exporter.core.markdown.html_visitor import HtmlMarkdownVisitor
from discord_chat_exporter.core.markdown.plaintext_visitor import PlainTextMarkdownVisitor


# ---------------------------------------------------------------------------
# Shared mock context
# ---------------------------------------------------------------------------


def _make_mock_context():
    """Build a mock ExportContext with basic lookups."""
    ctx = MagicMock()

    # Request mock
    ctx.request = MagicMock()
    ctx.request.should_format_markdown = True
    ctx.request.should_download_media = False
    ctx.request.export_format = ExportFormat.HTML_DARK
    ctx.request.is_utc_normalization_enabled = True

    # Members
    test_user = User(
        id=Snowflake(1001),
        is_bot=False,
        discriminator=None,
        name="testuser",
        display_name="Test User",
        avatar_url="https://cdn.discordapp.com/embed/avatars/0.png",
    )
    test_member = Member(
        user=test_user, display_name="Test Nick", avatar_url=None, role_ids=[]
    )

    members = {Snowflake(1001): test_member}
    ctx.try_get_member = MagicMock(side_effect=lambda mid: members.get(mid))
    ctx.populate_member_by_id = AsyncMock()
    ctx.populate_member = AsyncMock()

    # Channels
    test_channel = Channel(
        id=Snowflake(100),
        kind=ChannelKind.GUILD_TEXT_CHAT,
        guild_id=Snowflake(1),
        name="test-channel",
        last_message_id=Snowflake(999),
    )
    voice_channel = Channel(
        id=Snowflake(200),
        kind=ChannelKind.GUILD_VOICE_CHAT,
        guild_id=Snowflake(1),
        name="voice-room",
        last_message_id=Snowflake(999),
    )
    channels = {Snowflake(100): test_channel, Snowflake(200): voice_channel}
    ctx.try_get_channel = MagicMock(side_effect=lambda cid: channels.get(cid))

    # Roles
    test_role = Role(id=Snowflake(2001), name="Moderator", position=5, color="#ff5733")
    roles = {Snowflake(2001): test_role}
    ctx.try_get_role = MagicMock(side_effect=lambda rid: roles.get(rid))

    # resolve_asset_url returns the URL unchanged
    ctx.resolve_asset_url = AsyncMock(side_effect=lambda url: url)

    # Date formatting
    def format_date(instant, fmt="g"):
        dt = instant.astimezone(timezone.utc)
        formats = {
            "t": "%H:%M",
            "T": "%H:%M:%S",
            "d": "%m/%d/%Y",
            "D": "%B %d, %Y",
            "f": "%B %d, %Y %H:%M",
            "F": "%A, %B %d, %Y %H:%M",
            "g": "%m/%d/%Y %H:%M",
        }
        return dt.strftime(formats.get(fmt, fmt))

    ctx.format_date = MagicMock(side_effect=format_date)

    return ctx


# ===========================================================================
# HTML visitor tests
# ===========================================================================


class TestHtmlVisitor:
    """Tests for HtmlMarkdownVisitor.format()."""

    @pytest.mark.asyncio
    async def test_plain_text(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "Hello world")
        assert result == "Hello world"

    @pytest.mark.asyncio
    async def test_html_encoding(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(
            ctx, "<script>alert('xss')</script>"
        )
        assert "<script>" not in result
        assert "&lt;script&gt;" in result
        assert "alert(&#x27;xss&#x27;)" in result or "alert(" in result

    @pytest.mark.asyncio
    async def test_bold(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "**bold**")
        assert "<strong>bold</strong>" in result

    @pytest.mark.asyncio
    async def test_italic(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "*italic*")
        assert "<em>italic</em>" in result

    @pytest.mark.asyncio
    async def test_underline(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "__underline__")
        assert "<u>underline</u>" in result

    @pytest.mark.asyncio
    async def test_strikethrough(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "~~strike~~")
        assert "<s>strike</s>" in result

    @pytest.mark.asyncio
    async def test_spoiler(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "||spoiler||")
        assert "chatlog__markdown-spoiler" in result
        assert "spoiler" in result

    @pytest.mark.asyncio
    async def test_inline_code(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "`code`")
        assert "chatlog__markdown-pre--inline" in result
        assert "code" in result

    @pytest.mark.asyncio
    async def test_multi_line_code_block(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "```python\nprint('hi')\n```")
        assert "language-python" in result
        assert "print" in result

    @pytest.mark.asyncio
    async def test_multi_line_code_block_no_language(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "```\nsome code\n```")
        assert "nohighlight" in result

    @pytest.mark.asyncio
    async def test_user_mention_known(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "<@1001>")
        assert "chatlog__markdown-mention" in result
        assert "Test Nick" in result

    @pytest.mark.asyncio
    async def test_user_mention_unknown(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "<@9999>")
        assert "chatlog__markdown-mention" in result
        assert "Unknown" in result

    @pytest.mark.asyncio
    async def test_channel_mention_text(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "<#100>")
        assert "chatlog__markdown-mention" in result
        assert "#test-channel" in result

    @pytest.mark.asyncio
    async def test_channel_mention_voice(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "<#200>")
        assert "chatlog__markdown-mention" in result
        assert "\U0001F50A" in result  # speaker emoji

    @pytest.mark.asyncio
    async def test_role_mention(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "<@&2001>")
        assert "@Moderator" in result
        assert "chatlog__markdown-mention" in result
        # Should have colour styling from #ff5733
        assert "rgb(255, 87, 51)" in result

    @pytest.mark.asyncio
    async def test_everyone_mention(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "@everyone")
        assert "chatlog__markdown-mention" in result
        assert "@everyone" in result

    @pytest.mark.asyncio
    async def test_here_mention(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "@here")
        assert "chatlog__markdown-mention" in result
        assert "@here" in result

    @pytest.mark.asyncio
    async def test_auto_link(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "https://example.com")
        assert '<a href=' in result
        assert "https://example.com" in result

    @pytest.mark.asyncio
    async def test_discord_message_link(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(
            ctx, "https://discord.com/channels/1/100/5001"
        )
        assert "scrollToMessage" in result
        assert "5001" in result

    @pytest.mark.asyncio
    async def test_custom_emoji(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "<:LUL:123>")
        assert "<img" in result
        assert "chatlog__emoji" in result

    @pytest.mark.asyncio
    async def test_heading(self):
        ctx = _make_mock_context()
        # Heading regex requires a trailing newline
        result = await HtmlMarkdownVisitor.format(ctx, "# Title\n")
        assert "<h1>" in result
        assert "Title" in result
        assert "</h1>" in result

    @pytest.mark.asyncio
    async def test_heading_h2(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "## Subtitle\n")
        assert "<h2>" in result
        assert "Subtitle" in result

    @pytest.mark.asyncio
    async def test_quote(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "> quoted\n")
        assert "chatlog__markdown-quote" in result
        assert "quoted" in result

    @pytest.mark.asyncio
    async def test_timestamp(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "<t:1718452800:f>")
        assert "chatlog__markdown-timestamp" in result
        # The format_date mock formats "f" as "%B %d, %Y %H:%M"
        assert "June" in result

    @pytest.mark.asyncio
    async def test_timestamp_invalid(self):
        ctx = _make_mock_context()
        # <t:invalid:f> won't match the regex since it expects digits, so test
        # with an overflowing timestamp that triggers the except branch.
        result = await HtmlMarkdownVisitor.format(ctx, "<t:99999999999999999:f>")
        assert "Invalid date" in result

    @pytest.mark.asyncio
    async def test_jumbo_emoji(self):
        """Emoji-only message should get large emoji class."""
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(
            ctx, "<:LUL:123>", is_jumbo_allowed=True
        )
        assert "chatlog__emoji--large" in result

    @pytest.mark.asyncio
    async def test_non_jumbo_emoji(self):
        """Emoji mixed with text should NOT get large emoji class."""
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(
            ctx, "hello <:LUL:123>", is_jumbo_allowed=True
        )
        assert "chatlog__emoji--large" not in result

    @pytest.mark.asyncio
    async def test_jumbo_disabled(self):
        """Even emoji-only message should not be jumbo when is_jumbo_allowed=False."""
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(
            ctx, "<:LUL:123>", is_jumbo_allowed=False
        )
        assert "chatlog__emoji--large" not in result

    @pytest.mark.asyncio
    async def test_nested_bold_italic(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "***bold italic***")
        assert "<strong>" in result or "<em>" in result

    @pytest.mark.asyncio
    async def test_masked_link(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(
            ctx, "[click here](https://example.com)"
        )
        assert '<a href="https://example.com">' in result
        assert "click here" in result

    @pytest.mark.asyncio
    async def test_deleted_channel_mention(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "<#99999>")
        assert "deleted-channel" in result

    @pytest.mark.asyncio
    async def test_deleted_role_mention(self):
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "<@&99999>")
        assert "deleted-role" in result

    @pytest.mark.asyncio
    async def test_user_mention_with_exclamation(self):
        """<@!1001> is also a valid user mention syntax."""
        ctx = _make_mock_context()
        result = await HtmlMarkdownVisitor.format(ctx, "<@!1001>")
        assert "chatlog__markdown-mention" in result
        assert "Test Nick" in result

    @pytest.mark.asyncio
    async def test_role_mention_no_color(self):
        """Role with no color should have empty style."""
        ctx = _make_mock_context()
        no_color_role = Role(
            id=Snowflake(3001), name="NoColor", position=1, color=None
        )
        ctx.try_get_role = MagicMock(
            side_effect=lambda rid: (
                no_color_role if rid == Snowflake(3001) else None
            )
        )
        result = await HtmlMarkdownVisitor.format(ctx, "<@&3001>")
        assert "@NoColor" in result
        assert 'style=""' in result


# ===========================================================================
# Plain text visitor tests
# ===========================================================================


class TestPlainTextVisitor:
    """Tests for PlainTextMarkdownVisitor.format()."""

    @pytest.mark.asyncio
    async def test_plain_text_passthrough(self):
        ctx = _make_mock_context()
        result = await PlainTextMarkdownVisitor.format(ctx, "Hello world")
        assert result == "Hello world"

    @pytest.mark.asyncio
    async def test_custom_emoji(self):
        ctx = _make_mock_context()
        result = await PlainTextMarkdownVisitor.format(ctx, "<:LUL:123>")
        assert result == ":LUL:"

    @pytest.mark.asyncio
    async def test_user_mention_known(self):
        ctx = _make_mock_context()
        result = await PlainTextMarkdownVisitor.format(ctx, "<@1001>")
        assert result == "@Test Nick"

    @pytest.mark.asyncio
    async def test_user_mention_unknown(self):
        ctx = _make_mock_context()
        result = await PlainTextMarkdownVisitor.format(ctx, "<@9999>")
        assert result == "@Unknown"

    @pytest.mark.asyncio
    async def test_channel_mention_text(self):
        ctx = _make_mock_context()
        result = await PlainTextMarkdownVisitor.format(ctx, "<#100>")
        assert result == "#test-channel"

    @pytest.mark.asyncio
    async def test_channel_mention_voice(self):
        ctx = _make_mock_context()
        result = await PlainTextMarkdownVisitor.format(ctx, "<#200>")
        assert result == "#voice-room [voice]"

    @pytest.mark.asyncio
    async def test_role_mention(self):
        ctx = _make_mock_context()
        result = await PlainTextMarkdownVisitor.format(ctx, "<@&2001>")
        assert result == "@Moderator"

    @pytest.mark.asyncio
    async def test_everyone_mention(self):
        ctx = _make_mock_context()
        result = await PlainTextMarkdownVisitor.format(ctx, "@everyone")
        assert result == "@everyone"

    @pytest.mark.asyncio
    async def test_here_mention(self):
        ctx = _make_mock_context()
        result = await PlainTextMarkdownVisitor.format(ctx, "@here")
        assert result == "@here"

    @pytest.mark.asyncio
    async def test_timestamp(self):
        ctx = _make_mock_context()
        result = await PlainTextMarkdownVisitor.format(ctx, "<t:1718452800:f>")
        # "f" → "%B %d, %Y %H:%M"
        assert "June" in result
        assert "2024" in result

    @pytest.mark.asyncio
    async def test_timestamp_invalid(self):
        ctx = _make_mock_context()
        result = await PlainTextMarkdownVisitor.format(ctx, "<t:99999999999999999:f>")
        assert result == "Invalid date"

    @pytest.mark.asyncio
    async def test_formatting_preserved_as_is(self):
        """Minimal parser does NOT parse formatting, so markdown syntax passes through."""
        ctx = _make_mock_context()
        result = await PlainTextMarkdownVisitor.format(ctx, "**bold**")
        assert result == "**bold**"

    @pytest.mark.asyncio
    async def test_deleted_channel_mention(self):
        ctx = _make_mock_context()
        result = await PlainTextMarkdownVisitor.format(ctx, "<#99999>")
        assert result == "#deleted-channel"

    @pytest.mark.asyncio
    async def test_deleted_role_mention(self):
        ctx = _make_mock_context()
        result = await PlainTextMarkdownVisitor.format(ctx, "<@&99999>")
        assert result == "@deleted-role"

    @pytest.mark.asyncio
    async def test_user_mention_with_exclamation(self):
        ctx = _make_mock_context()
        result = await PlainTextMarkdownVisitor.format(ctx, "<@!1001>")
        assert result == "@Test Nick"

    @pytest.mark.asyncio
    async def test_mixed_text_and_mentions(self):
        ctx = _make_mock_context()
        result = await PlainTextMarkdownVisitor.format(
            ctx, "Hey <@1001>, check <#100>"
        )
        assert result == "Hey @Test Nick, check #test-channel"

    @pytest.mark.asyncio
    async def test_timestamp_default_format(self):
        """Timestamp with no format should use default 'g' format."""
        ctx = _make_mock_context()
        result = await PlainTextMarkdownVisitor.format(ctx, "<t:1718452800>")
        # "g" → "%m/%d/%Y %H:%M"
        assert "06/15/2024" in result
