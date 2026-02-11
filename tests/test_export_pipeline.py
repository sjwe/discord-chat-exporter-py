"""Unit tests for export pipeline: ExportFormat, exceptions, ExportRequest, ExportContext, MessageExporter."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from discord_chat_exporter.core.discord.models.channel import Channel, ChannelKind
from discord_chat_exporter.core.discord.models.guild import Guild
from discord_chat_exporter.core.discord.models.member import Member
from discord_chat_exporter.core.discord.models.message import Message, MessageKind
from discord_chat_exporter.core.discord.models.role import Role
from discord_chat_exporter.core.discord.models.user import User
from discord_chat_exporter.core.discord.snowflake import Snowflake
from discord_chat_exporter.core.exceptions import ChannelEmptyError, DiscordChatExporterError
from discord_chat_exporter.core.exporting.context import ExportContext
from discord_chat_exporter.core.exporting.format import ExportFormat
from discord_chat_exporter.core.exporting.message_exporter import _get_partition_file_path
from discord_chat_exporter.core.exporting.request import (
    ExportRequest,
    _escape_filename,
    _format_path,
)
from tests.conftest import MockDiscordClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

_AVATAR = "https://cdn.discordapp.com/embed/avatars/0.png"


def _guild(name: str = "Test Guild") -> Guild:
    return Guild(id=Snowflake(1), name=name, icon_url=_AVATAR)


def _user(uid: int = 1001, name: str = "testuser", display: str = "Test User") -> User:
    return User(
        id=Snowflake(uid), is_bot=False, discriminator=None,
        name=name, display_name=display, avatar_url=_AVATAR,
    )


def _channel(
    cid: int = 100, name: str = "test-channel", parent: Channel | None = None,
    position: int | None = None,
) -> Channel:
    return Channel(
        id=Snowflake(cid), kind=ChannelKind.GUILD_TEXT_CHAT, guild_id=Snowflake(1),
        name=name, parent=parent, position=position,
        topic="Test topic", last_message_id=Snowflake(999),
    )


def _msg(
    mid: int = 5001,
    kind: MessageKind = MessageKind.DEFAULT,
    content: str = "",
    author: User | None = None,
    mentioned_users: list[User] | None = None,
    call_ended_timestamp: datetime | None = None,
) -> Message:
    return Message(
        id=Snowflake(mid), kind=kind,
        author=author or _user(),
        timestamp=_TS, content=content,
        mentioned_users=mentioned_users or [],
        call_ended_timestamp=call_ended_timestamp,
    )


def _request(
    output_path: str = "/tmp/test_output.txt",
    fmt: ExportFormat = ExportFormat.PLAIN_TEXT,
    guild: Guild | None = None,
    channel: Channel | None = None,
    after: Snowflake | None = None,
    before: Snowflake | None = None,
    assets_dir_path: str | None = None,
    is_utc: bool = False,
) -> ExportRequest:
    return ExportRequest(
        guild=guild or _guild(),
        channel=channel or _channel(),
        output_path=output_path,
        export_format=fmt,
        after=after, before=before,
        assets_dir_path=assets_dir_path,
        is_utc_normalization_enabled=is_utc,
    )


def _context(
    channels: list[Channel] | None = None,
    roles: list[Role] | None = None,
    members: dict[Snowflake, Member] | None = None,
    is_utc: bool = True,
) -> ExportContext:
    client = MockDiscordClient(
        channels=channels or [],
        roles=roles or [],
        members=members or {},
    )
    req = _request(is_utc=is_utc)
    return ExportContext(client, req)


# ===================================================================
# ExportFormat
# ===================================================================


class TestExportFormat:
    def test_file_extension_plain_text(self):
        assert ExportFormat.PLAIN_TEXT.file_extension == "txt"

    def test_file_extension_html_dark(self):
        assert ExportFormat.HTML_DARK.file_extension == "html"

    def test_file_extension_html_light(self):
        assert ExportFormat.HTML_LIGHT.file_extension == "html"

    def test_file_extension_csv(self):
        assert ExportFormat.CSV.file_extension == "csv"

    def test_file_extension_json(self):
        assert ExportFormat.JSON.file_extension == "json"

    def test_display_name_plain_text(self):
        assert ExportFormat.PLAIN_TEXT.display_name == "TXT"

    def test_display_name_html_dark(self):
        assert ExportFormat.HTML_DARK.display_name == "HTML (Dark)"

    def test_display_name_html_light(self):
        assert ExportFormat.HTML_LIGHT.display_name == "HTML (Light)"

    def test_display_name_csv(self):
        assert ExportFormat.CSV.display_name == "CSV"

    def test_display_name_json(self):
        assert ExportFormat.JSON.display_name == "JSON"

    def test_is_html_dark(self):
        assert ExportFormat.HTML_DARK.is_html is True

    def test_is_html_light(self):
        assert ExportFormat.HTML_LIGHT.is_html is True

    def test_is_html_plain_text(self):
        assert ExportFormat.PLAIN_TEXT.is_html is False

    def test_is_html_csv(self):
        assert ExportFormat.CSV.is_html is False

    def test_is_html_json(self):
        assert ExportFormat.JSON.is_html is False


# ===================================================================
# Exceptions
# ===================================================================


class TestDiscordChatExporterError:
    def test_message_preserved(self):
        err = DiscordChatExporterError("something broke")
        assert err.args[0] == "something broke"

    def test_is_fatal_default_false(self):
        err = DiscordChatExporterError("msg")
        assert err.is_fatal is False

    def test_is_fatal_true(self):
        err = DiscordChatExporterError("fatal", is_fatal=True)
        assert err.is_fatal is True

    def test_is_exception(self):
        assert issubclass(DiscordChatExporterError, Exception)


class TestChannelEmptyError:
    def test_is_subclass(self):
        assert issubclass(ChannelEmptyError, DiscordChatExporterError)

    def test_inherits_is_fatal(self):
        err = ChannelEmptyError("empty", is_fatal=False)
        assert err.is_fatal is False

    def test_can_be_caught_as_base(self):
        with pytest.raises(DiscordChatExporterError):
            raise ChannelEmptyError("no messages")


# ===================================================================
# _escape_filename
# ===================================================================


class TestEscapeFilename:
    def test_removes_angle_brackets(self):
        assert "<" not in _escape_filename("a<b>c")

    def test_removes_colon(self):
        assert ":" not in _escape_filename("a:b")

    def test_removes_double_quote(self):
        assert '"' not in _escape_filename('a"b')

    def test_removes_slash(self):
        assert "/" not in _escape_filename("a/b")

    def test_removes_backslash(self):
        assert "\\" not in _escape_filename("a\\b")

    def test_removes_pipe(self):
        assert "|" not in _escape_filename("a|b")

    def test_removes_question_mark(self):
        assert "?" not in _escape_filename("a?b")

    def test_removes_asterisk(self):
        assert "*" not in _escape_filename("a*b")

    def test_replaces_double_dot(self):
        assert ".." not in _escape_filename("foo..bar")

    def test_preserves_normal_chars(self):
        assert _escape_filename("hello world") == "hello world"

    def test_combined_special_chars(self):
        result = _escape_filename('a<b>c:d"e/f\\g|h?i*j')
        for ch in '<>:"/\\|?*':
            assert ch not in result


# ===================================================================
# _format_path
# ===================================================================


class TestFormatPath:
    def test_guild_id(self):
        g = _guild()
        ch = _channel()
        assert "1" in _format_path("%g", g, ch, None, None)

    def test_guild_name(self):
        g = _guild("MyGuild")
        ch = _channel()
        assert "MyGuild" in _format_path("%G", g, ch, None, None)

    def test_channel_id(self):
        g = _guild()
        ch = _channel(cid=42)
        assert "42" in _format_path("%c", g, ch, None, None)

    def test_channel_name(self):
        g = _guild()
        ch = _channel(name="general")
        assert "general" in _format_path("%C", g, ch, None, None)

    def test_parent_id_empty_without_parent(self):
        g = _guild()
        ch = _channel()
        assert _format_path("%t", g, ch, None, None) == ""

    def test_parent_name_empty_without_parent(self):
        g = _guild()
        ch = _channel()
        assert _format_path("%T", g, ch, None, None) == ""

    def test_parent_id_with_parent(self):
        g = _guild()
        parent = _channel(cid=50, name="Category")
        ch = _channel(parent=parent)
        assert "50" in _format_path("%t", g, ch, None, None)

    def test_parent_name_with_parent(self):
        g = _guild()
        parent = _channel(cid=50, name="Category")
        ch = _channel(parent=parent)
        assert "Category" in _format_path("%T", g, ch, None, None)

    def test_channel_position(self):
        g = _guild()
        ch = _channel(position=7)
        assert "7" in _format_path("%p", g, ch, None, None)

    def test_parent_position_without_parent(self):
        g = _guild()
        ch = _channel()
        assert _format_path("%P", g, ch, None, None) == "0"

    def test_after_date(self):
        g = _guild()
        ch = _channel()
        after = Snowflake.from_date(datetime(2024, 1, 15, tzinfo=timezone.utc))
        result = _format_path("%a", g, ch, after, None)
        assert "2024-01-15" in result

    def test_before_date(self):
        g = _guild()
        ch = _channel()
        before = Snowflake.from_date(datetime(2024, 6, 30, tzinfo=timezone.utc))
        result = _format_path("%b", g, ch, None, before)
        assert "2024-06-30" in result

    def test_current_date(self):
        g = _guild()
        ch = _channel()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        result = _format_path("%d", g, ch, None, None)
        assert today in result

    def test_literal_percent(self):
        g = _guild()
        ch = _channel()
        assert _format_path("%%", g, ch, None, None) == "%"

    def test_after_empty_when_none(self):
        g = _guild()
        ch = _channel()
        assert _format_path("%a", g, ch, None, None) == ""


# ===================================================================
# ExportRequest
# ===================================================================


class TestExportRequest:
    def test_output_file_path_is_absolute(self):
        req = _request(output_path="/tmp/out.txt")
        assert os.path.isabs(req.output_file_path)

    def test_output_dir_path(self):
        req = _request(output_path="/tmp/out.txt")
        assert req.output_dir_path == os.path.dirname(req.output_file_path)

    def test_assets_dir_path_default(self):
        req = _request(output_path="/tmp/out.txt")
        assert req.assets_dir_path.endswith("_Files" + os.sep)

    def test_assets_dir_path_custom(self):
        req = _request(output_path="/tmp/out.txt", assets_dir_path="/tmp/custom_assets")
        assert "custom_assets" in req.assets_dir_path
        assert os.path.isabs(req.assets_dir_path)

    def test_default_output_filename_basic(self):
        g = _guild("My Server")
        ch = _channel(cid=200, name="chat")
        name = ExportRequest.get_default_output_filename(g, ch, ExportFormat.PLAIN_TEXT)
        assert "My Server" in name
        assert "chat" in name
        assert "200" in name
        assert name.endswith(".txt")

    def test_default_output_filename_with_parent(self):
        g = _guild("Server")
        parent = _channel(cid=50, name="Category")
        ch = _channel(cid=100, name="general", parent=parent)
        name = ExportRequest.get_default_output_filename(g, ch, ExportFormat.CSV)
        assert "Category" in name
        assert "general" in name
        assert name.endswith(".csv")

    def test_default_output_filename_with_after(self):
        g = _guild()
        ch = _channel()
        after = Snowflake.from_date(datetime(2024, 3, 1, tzinfo=timezone.utc))
        name = ExportRequest.get_default_output_filename(g, ch, ExportFormat.JSON, after=after)
        assert "after" in name
        assert "2024-03-01" in name

    def test_default_output_filename_with_both_dates(self):
        g = _guild()
        ch = _channel()
        after = Snowflake.from_date(datetime(2024, 1, 1, tzinfo=timezone.utc))
        before = Snowflake.from_date(datetime(2024, 6, 30, tzinfo=timezone.utc))
        name = ExportRequest.get_default_output_filename(
            g, ch, ExportFormat.HTML_DARK, after=after, before=before,
        )
        assert "to" in name
        assert name.endswith(".html")

    def test_default_output_filename_with_before_only(self):
        g = _guild()
        ch = _channel()
        before = Snowflake.from_date(datetime(2024, 12, 31, tzinfo=timezone.utc))
        name = ExportRequest.get_default_output_filename(
            g, ch, ExportFormat.PLAIN_TEXT, before=before,
        )
        assert "before" in name

    def test_format_stored(self):
        req = _request(fmt=ExportFormat.JSON)
        assert req.export_format == ExportFormat.JSON

    def test_utc_normalization_stored(self):
        req = _request(is_utc=True)
        assert req.is_utc_normalization_enabled is True


# ===================================================================
# ExportContext – date helpers
# ===================================================================


class TestExportContextDateHelpers:
    def test_normalize_date_utc_enabled(self):
        ctx = _context(is_utc=True)
        dt = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone(timedelta(hours=5)))
        result = ctx.normalize_date(dt)
        assert result.tzinfo == timezone.utc
        assert result.hour == 7

    def test_normalize_date_utc_disabled(self):
        ctx = _context(is_utc=False)
        dt = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = ctx.normalize_date(dt)
        # Should convert to local timezone (not UTC unless local == UTC)
        assert result.tzinfo is not None

    def test_format_date_short_time(self):
        ctx = _context(is_utc=True)
        dt = datetime(2024, 6, 15, 14, 30, 0, tzinfo=timezone.utc)
        assert ctx.format_date(dt, "t") == "14:30"

    def test_format_date_long_time(self):
        ctx = _context(is_utc=True)
        dt = datetime(2024, 6, 15, 14, 30, 45, tzinfo=timezone.utc)
        assert ctx.format_date(dt, "T") == "14:30:45"

    def test_format_date_short_date(self):
        ctx = _context(is_utc=True)
        dt = datetime(2024, 6, 15, 14, 30, 0, tzinfo=timezone.utc)
        assert ctx.format_date(dt, "d") == "06/15/2024"

    def test_format_date_long_date(self):
        ctx = _context(is_utc=True)
        dt = datetime(2024, 6, 15, 14, 30, 0, tzinfo=timezone.utc)
        assert ctx.format_date(dt, "D") == "June 15, 2024"

    def test_format_date_long_date_short_time(self):
        ctx = _context(is_utc=True)
        dt = datetime(2024, 6, 15, 14, 30, 0, tzinfo=timezone.utc)
        assert ctx.format_date(dt, "f") == "June 15, 2024 14:30"

    def test_format_date_full(self):
        ctx = _context(is_utc=True)
        dt = datetime(2024, 6, 15, 14, 30, 0, tzinfo=timezone.utc)
        result = ctx.format_date(dt, "F")
        assert "Saturday" in result
        assert "June 15, 2024" in result
        assert "14:30" in result

    def test_format_date_default_g(self):
        ctx = _context(is_utc=True)
        dt = datetime(2024, 6, 15, 14, 30, 0, tzinfo=timezone.utc)
        assert ctx.format_date(dt) == "06/15/2024 14:30"


# ===================================================================
# ExportContext – populate & lookups
# ===================================================================


class TestExportContextPopulate:
    @pytest.mark.asyncio
    async def test_populate_channels_and_roles(self):
        ch = _channel(cid=200, name="general")
        role = Role(id=Snowflake(3001), name="Admin", position=10, color="#ff0000")
        ctx = _context(channels=[ch], roles=[role])
        await ctx.populate_channels_and_roles()
        assert ctx.try_get_channel(Snowflake(200)) is ch
        assert ctx.try_get_role(Snowflake(3001)) is role

    @pytest.mark.asyncio
    async def test_channels_stored_by_id(self):
        ch1 = _channel(cid=10, name="a")
        ch2 = _channel(cid=20, name="b")
        ctx = _context(channels=[ch1, ch2])
        await ctx.populate_channels_and_roles()
        assert ctx.try_get_channel(Snowflake(10)) is ch1
        assert ctx.try_get_channel(Snowflake(20)) is ch2

    @pytest.mark.asyncio
    async def test_roles_stored_by_id(self):
        r1 = Role(id=Snowflake(301), name="R1", position=1)
        r2 = Role(id=Snowflake(302), name="R2", position=2)
        ctx = _context(roles=[r1, r2])
        await ctx.populate_channels_and_roles()
        assert ctx.try_get_role(Snowflake(301)) is r1
        assert ctx.try_get_role(Snowflake(302)) is r2

    @pytest.mark.asyncio
    async def test_try_get_channel_returns_none_if_missing(self):
        ctx = _context()
        await ctx.populate_channels_and_roles()
        assert ctx.try_get_channel(Snowflake(9999)) is None

    @pytest.mark.asyncio
    async def test_try_get_role_returns_none_if_missing(self):
        ctx = _context()
        await ctx.populate_channels_and_roles()
        assert ctx.try_get_role(Snowflake(9999)) is None


class TestExportContextMembers:
    @pytest.mark.asyncio
    async def test_populate_member_stores_in_cache(self):
        user = _user(uid=1001)
        member = Member(user=user, role_ids=[])
        ctx = _context(members={Snowflake(1001): member})
        await ctx.populate_member(user)
        assert ctx.try_get_member(Snowflake(1001)) is member

    @pytest.mark.asyncio
    async def test_populate_member_no_refetch(self):
        user = _user(uid=1001)
        member = Member(user=user, role_ids=[])
        client = MockDiscordClient(members={Snowflake(1001): member})
        req = _request(is_utc=True)
        ctx = ExportContext(client, req)

        # Wrap get_member to count calls
        original = client.get_member
        call_count = 0

        async def counting_get_member(guild_id, user_id):
            nonlocal call_count
            call_count += 1
            return await original(guild_id, user_id)

        client.get_member = counting_get_member

        await ctx.populate_member(user)
        await ctx.populate_member(user)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_populate_member_creates_fallback_if_none(self):
        user = _user(uid=2002, display="Fallback User")
        # Client returns None for this member
        client = MockDiscordClient(members={})
        req = _request(is_utc=True)
        ctx = ExportContext(client, req)
        await ctx.populate_member(user)
        member = ctx.try_get_member(Snowflake(2002))
        assert member is not None
        assert member.user.id == Snowflake(2002)

    @pytest.mark.asyncio
    async def test_get_member_returns_none_if_not_populated(self):
        ctx = _context()
        assert ctx.try_get_member(Snowflake(9999)) is None


# ===================================================================
# ExportContext – roles & colors
# ===================================================================


class TestExportContextRolesAndColors:
    @pytest.mark.asyncio
    async def test_get_user_roles_sorted_by_position_desc(self):
        user = _user(uid=1001)
        r_low = Role(id=Snowflake(301), name="Low", position=1, color="#aaa")
        r_high = Role(id=Snowflake(302), name="High", position=10, color="#bbb")
        member = Member(user=user, role_ids=[Snowflake(301), Snowflake(302)])
        ctx = _context(roles=[r_low, r_high], members={Snowflake(1001): member})
        await ctx.populate_channels_and_roles()
        await ctx.populate_member(user)

        roles = ctx.get_user_roles(Snowflake(1001))
        assert len(roles) == 2
        assert roles[0].position > roles[1].position
        assert roles[0].name == "High"

    @pytest.mark.asyncio
    async def test_get_user_roles_empty_for_unknown_member(self):
        ctx = _context()
        assert ctx.get_user_roles(Snowflake(9999)) == []

    @pytest.mark.asyncio
    async def test_try_get_user_color_returns_highest_position(self):
        user = _user(uid=1001)
        r_low = Role(id=Snowflake(301), name="Low", position=1, color="#111111")
        r_high = Role(id=Snowflake(302), name="High", position=10, color="#222222")
        member = Member(user=user, role_ids=[Snowflake(301), Snowflake(302)])
        ctx = _context(roles=[r_low, r_high], members={Snowflake(1001): member})
        await ctx.populate_channels_and_roles()
        await ctx.populate_member(user)

        color = ctx.try_get_user_color(Snowflake(1001))
        assert color == "#222222"

    @pytest.mark.asyncio
    async def test_try_get_user_color_none_if_no_colored_roles(self):
        user = _user(uid=1001)
        r = Role(id=Snowflake(301), name="NoColor", position=1, color=None)
        member = Member(user=user, role_ids=[Snowflake(301)])
        ctx = _context(roles=[r], members={Snowflake(1001): member})
        await ctx.populate_channels_and_roles()
        await ctx.populate_member(user)

        assert ctx.try_get_user_color(Snowflake(1001)) is None

    @pytest.mark.asyncio
    async def test_try_get_user_color_none_for_unknown_member(self):
        ctx = _context()
        assert ctx.try_get_user_color(Snowflake(9999)) is None


# ===================================================================
# ExportContext – get_fallback_content
# ===================================================================


class TestGetFallbackContent:
    def test_recipient_add_with_mentioned_user(self):
        mentioned = _user(uid=2001, display="Alice")
        msg = _msg(kind=MessageKind.RECIPIENT_ADD, mentioned_users=[mentioned])
        assert ExportContext.get_fallback_content(msg) == "Added Alice to the group."

    def test_recipient_add_without_mentioned_user(self):
        msg = _msg(kind=MessageKind.RECIPIENT_ADD)
        assert ExportContext.get_fallback_content(msg) == "Added a recipient."

    def test_recipient_remove_self(self):
        user = _user(uid=1001)
        msg = _msg(kind=MessageKind.RECIPIENT_REMOVE, author=user, mentioned_users=[user])
        assert ExportContext.get_fallback_content(msg) == "Left the group."

    def test_recipient_remove_other(self):
        author = _user(uid=1001)
        removed = _user(uid=2001, display="Bob")
        msg = _msg(kind=MessageKind.RECIPIENT_REMOVE, author=author, mentioned_users=[removed])
        assert ExportContext.get_fallback_content(msg) == "Removed Bob from the group."

    def test_recipient_remove_without_mentioned(self):
        msg = _msg(kind=MessageKind.RECIPIENT_REMOVE)
        assert ExportContext.get_fallback_content(msg) == "Removed a recipient."

    def test_call_with_ended_timestamp(self):
        start = _TS
        end = _TS + timedelta(minutes=5)
        msg = _msg(kind=MessageKind.CALL, call_ended_timestamp=end)
        result = ExportContext.get_fallback_content(msg)
        assert "5" in result
        assert "minutes" in result

    def test_call_without_ended_timestamp(self):
        msg = _msg(kind=MessageKind.CALL)
        assert ExportContext.get_fallback_content(msg) == "Started a call that lasted 0 minutes."

    def test_channel_name_change(self):
        msg = _msg(kind=MessageKind.CHANNEL_NAME_CHANGE, content="new-name")
        assert ExportContext.get_fallback_content(msg) == "Changed the channel name: new-name"

    def test_channel_name_change_empty_content(self):
        msg = _msg(kind=MessageKind.CHANNEL_NAME_CHANGE, content="  ")
        assert ExportContext.get_fallback_content(msg) == "Changed the channel name."

    def test_channel_icon_change(self):
        msg = _msg(kind=MessageKind.CHANNEL_ICON_CHANGE)
        assert ExportContext.get_fallback_content(msg) == "Changed the channel icon."

    def test_channel_pinned_message(self):
        msg = _msg(kind=MessageKind.CHANNEL_PINNED_MESSAGE)
        assert ExportContext.get_fallback_content(msg) == "Pinned a message."

    def test_thread_created(self):
        msg = _msg(kind=MessageKind.THREAD_CREATED)
        assert ExportContext.get_fallback_content(msg) == "Started a thread."

    def test_guild_member_join(self):
        msg = _msg(kind=MessageKind.GUILD_MEMBER_JOIN)
        assert ExportContext.get_fallback_content(msg) == "Joined the server."

    def test_default_returns_content(self):
        msg = _msg(kind=MessageKind.DEFAULT, content="Hello world")
        assert ExportContext.get_fallback_content(msg) == "Hello world"


# ===================================================================
# _get_partition_file_path
# ===================================================================


class TestGetPartitionFilePath:
    def test_index_zero_returns_base(self):
        assert _get_partition_file_path("/tmp/file.txt", 0) == "/tmp/file.txt"

    def test_index_one(self):
        result = _get_partition_file_path("/tmp/file.txt", 1)
        assert result == "/tmp/file [part 2].txt"

    def test_index_two(self):
        result = _get_partition_file_path("/tmp/file.txt", 2)
        assert result == "/tmp/file [part 3].txt"

    def test_with_directory(self):
        result = _get_partition_file_path("/home/user/exports/chat.json", 1)
        assert result == "/home/user/exports/chat [part 2].json"

    def test_negative_index_returns_base(self):
        assert _get_partition_file_path("/tmp/file.txt", -1) == "/tmp/file.txt"

    def test_preserves_extension(self):
        result = _get_partition_file_path("/tmp/export.html", 3)
        assert result.endswith(".html")
        assert "[part 4]" in result
