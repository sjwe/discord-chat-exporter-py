"""Shared fixtures and mock client for integration tests."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from discord_chat_exporter.core.discord.models.attachment import Attachment
from discord_chat_exporter.core.discord.models.channel import Channel, ChannelKind
from discord_chat_exporter.core.discord.models.embed import Embed, EmbedField, EmbedKind
from discord_chat_exporter.core.discord.models.emoji import Emoji
from discord_chat_exporter.core.discord.models.guild import Guild
from discord_chat_exporter.core.discord.models.member import Member
from discord_chat_exporter.core.discord.models.message import (
    Message,
    MessageKind,
    MessageReference,
)
from discord_chat_exporter.core.discord.models.reaction import Reaction
from discord_chat_exporter.core.discord.models.role import Role
from discord_chat_exporter.core.discord.models.user import User
from discord_chat_exporter.core.discord.snowflake import Snowflake
from discord_chat_exporter.core.exporting.channel_exporter import ChannelExporter
from discord_chat_exporter.core.exporting.format import ExportFormat
from discord_chat_exporter.core.exporting.request import ExportRequest


# ---------------------------------------------------------------------------
# Mock Discord client
# ---------------------------------------------------------------------------


class MockDiscordClient:
    """Duck-typed mock matching the methods ExportContext actually calls."""

    def __init__(
        self,
        channels: list[Channel] | None = None,
        roles: list[Role] | None = None,
        messages: list[Message] | None = None,
        members: dict[Snowflake, Member] | None = None,
    ) -> None:
        self._channels = channels or []
        self._roles = roles or []
        self._messages = messages or []
        self._members = members or {}

    async def get_channels(self, guild_id: Snowflake) -> list[Channel]:
        return self._channels

    async def get_roles(self, guild_id: Snowflake) -> list[Role]:
        return self._roles

    async def try_get_member(
        self, guild_id: Snowflake, user_id: Snowflake
    ) -> Member | None:
        member = self._members.get(user_id)
        if member is not None:
            return member
        # Fall back to creating a fallback member from the messages
        for msg in self._messages:
            for user in msg.get_referenced_users():
                if user.id == user_id:
                    return Member.create_fallback(user)
        return None

    async def get_messages(
        self,
        channel_id: Snowflake,
        after: Snowflake | None = None,
        before: Snowflake | None = None,
    ):
        for msg in self._messages:
            if after and msg.id <= after:
                continue
            if before and msg.id >= before:
                continue
            yield msg


# ---------------------------------------------------------------------------
# Model fixtures
# ---------------------------------------------------------------------------

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def mock_guild() -> Guild:
    return Guild(
        id=Snowflake(1),
        name="Test Guild",
        icon_url="https://cdn.discordapp.com/embed/avatars/0.png",
    )


@pytest.fixture
def mock_channel() -> Channel:
    return Channel(
        id=Snowflake(100),
        kind=ChannelKind.GUILD_TEXT_CHAT,
        guild_id=Snowflake(1),
        name="test-channel",
        topic="Test channel topic",
        last_message_id=Snowflake(999),
    )


@pytest.fixture
def mock_user() -> User:
    return User(
        id=Snowflake(1001),
        is_bot=False,
        discriminator=None,
        name="testuser",
        display_name="Test User",
        avatar_url="https://cdn.discordapp.com/embed/avatars/0.png",
    )


@pytest.fixture
def mock_user_2() -> User:
    return User(
        id=Snowflake(1002),
        is_bot=False,
        discriminator=None,
        name="otheruser",
        display_name="Other User",
        avatar_url="https://cdn.discordapp.com/embed/avatars/1.png",
    )


@pytest.fixture
def mock_role() -> Role:
    return Role(
        id=Snowflake(2001),
        name="Moderator",
        position=5,
        color="#ff5733",
    )


@pytest.fixture
def mock_messages(mock_user, mock_user_2) -> list[Message]:
    """Five messages exercising different features."""
    # 1. Basic text message
    msg_basic = Message(
        id=Snowflake(5001),
        kind=MessageKind.DEFAULT,
        author=mock_user,
        timestamp=_TS,
        content="Hello, world!",
    )

    # 2. Message with attachment
    msg_attachment = Message(
        id=Snowflake(5002),
        kind=MessageKind.DEFAULT,
        author=mock_user_2,
        timestamp=_TS,
        content="Check out this file",
        attachments=[
            Attachment(
                id=Snowflake(6001),
                url="https://cdn.discordapp.com/attachments/100/6001/image.png",
                file_name="image.png",
                file_size_bytes=1024,
                width=800,
                height=600,
            )
        ],
    )

    # 3. Message with reaction
    msg_reaction = Message(
        id=Snowflake(5003),
        kind=MessageKind.DEFAULT,
        author=mock_user,
        timestamp=_TS,
        content="React to this!",
        reactions=[
            Reaction(
                emoji=Emoji(id=None, name="\U0001f44d", is_animated=False),
                count=3,
            ),
        ],
    )

    # 4. Message with embed
    msg_embed = Message(
        id=Snowflake(5004),
        kind=MessageKind.DEFAULT,
        author=mock_user_2,
        timestamp=_TS,
        content="",
        embeds=[
            Embed(
                title="Example Embed",
                kind=EmbedKind.RICH,
                description="This is an embed description",
                color="#3498db",
                fields=[
                    EmbedField(name="Field 1", value="Value 1", is_inline=True),
                ],
            )
        ],
    )

    # 5. Reply message
    msg_reply = Message(
        id=Snowflake(5005),
        kind=MessageKind.REPLY,
        author=mock_user_2,
        timestamp=_TS,
        content="This is a reply",
        reference=MessageReference(
            message_id=Snowflake(5001),
            channel_id=Snowflake(100),
            guild_id=Snowflake(1),
        ),
        referenced_message=msg_basic,
    )

    return [msg_basic, msg_attachment, msg_reaction, msg_embed, msg_reply]


# ---------------------------------------------------------------------------
# Export helper
# ---------------------------------------------------------------------------


async def export_to_format(
    tmp_path,
    fmt: ExportFormat,
    guild: Guild,
    channel: Channel,
    messages: list[Message],
    roles: list[Role] | None = None,
    partition_limit=None,
    message_filter=None,
) -> str:
    """Run ChannelExporter.export() and return the output file content as a string."""
    output_path = os.path.join(str(tmp_path), f"export.{fmt.file_extension}")

    client = MockDiscordClient(
        channels=[channel],
        roles=roles or [],
        messages=messages,
    )

    request = ExportRequest(
        guild=guild,
        channel=channel,
        output_path=output_path,
        export_format=fmt,
        partition_limit=partition_limit,
        message_filter=message_filter,
        is_utc_normalization_enabled=True,
    )

    exporter = ChannelExporter(client)
    await exporter.export(request)

    with open(request.output_file_path, encoding="utf-8") as f:
        return f.read()
