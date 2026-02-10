"""Unit tests for message filters and combinators."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from discord_chat_exporter.core.discord.models.attachment import Attachment
from discord_chat_exporter.core.discord.models.embed import (
    Embed,
    EmbedAuthor,
    EmbedField,
    EmbedFooter,
    EmbedKind,
)
from discord_chat_exporter.core.discord.models.emoji import Emoji
from discord_chat_exporter.core.discord.models.message import Message, MessageKind
from discord_chat_exporter.core.discord.models.reaction import Reaction
from discord_chat_exporter.core.discord.models.user import User
from discord_chat_exporter.core.discord.snowflake import Snowflake
from discord_chat_exporter.core.exporting.filtering.base import (
    MessageFilter,
    NullMessageFilter,
)
from discord_chat_exporter.core.exporting.filtering.combinators import (
    BinaryExpressionKind,
    BinaryExpressionMessageFilter,
    NegatedMessageFilter,
)
from discord_chat_exporter.core.exporting.filtering.filters import (
    ContainsMessageFilter,
    FromMessageFilter,
    HasMessageFilter,
    MentionsMessageFilter,
    ReactionMessageFilter,
)

_TS = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _make_user(
    name: str = "testuser",
    display_name: str = "Test User",
    uid: int = 1001,
    discriminator: int | None = None,
    is_bot: bool = False,
) -> User:
    return User(
        id=Snowflake(uid),
        is_bot=is_bot,
        discriminator=discriminator,
        name=name,
        display_name=display_name,
        avatar_url="https://cdn.discordapp.com/embed/avatars/0.png",
    )


def _make_message(
    content: str = "",
    user: User | None = None,
    attachments: list[Attachment] | None = None,
    embeds: list[Embed] | None = None,
    reactions: list[Reaction] | None = None,
    mentioned_users: list[User] | None = None,
    is_pinned: bool = False,
    msg_id: int = 5001,
) -> Message:
    return Message(
        id=Snowflake(msg_id),
        kind=MessageKind.DEFAULT,
        author=user or _make_user(),
        timestamp=_TS,
        content=content,
        attachments=attachments or [],
        embeds=embeds or [],
        reactions=reactions or [],
        mentioned_users=mentioned_users or [],
        is_pinned=is_pinned,
    )


# ===================================================================
# NullMessageFilter
# ===================================================================


class TestNullMessageFilter:
    def test_always_true(self):
        f = NullMessageFilter()
        assert f.is_match(_make_message("anything"))

    def test_empty_message(self):
        f = NullMessageFilter()
        assert f.is_match(_make_message(""))

    def test_factory(self):
        f = MessageFilter.null()
        assert isinstance(f, NullMessageFilter)
        assert f.is_match(_make_message("test"))


# ===================================================================
# ContainsMessageFilter
# ===================================================================


class TestContainsMessageFilter:
    def test_basic_match(self):
        f = ContainsMessageFilter("hello")
        assert f.is_match(_make_message("hello world"))

    def test_no_match(self):
        f = ContainsMessageFilter("goodbye")
        assert not f.is_match(_make_message("hello world"))

    def test_case_insensitive(self):
        f = ContainsMessageFilter("HELLO")
        assert f.is_match(_make_message("hello world"))

    def test_word_boundary_no_partial(self):
        f = ContainsMessageFilter("max")
        assert not f.is_match(_make_message("maximum"))

    def test_word_boundary_with_punctuation(self):
        f = ContainsMessageFilter("max")
        assert f.is_match(_make_message("(max)"))

    def test_word_boundary_with_period(self):
        f = ContainsMessageFilter("max")
        assert f.is_match(_make_message("set to max."))

    def test_word_boundary_start_of_string(self):
        f = ContainsMessageFilter("hello")
        assert f.is_match(_make_message("hello!"))

    def test_empty_content(self):
        f = ContainsMessageFilter("test")
        assert not f.is_match(_make_message(""))

    def test_whitespace_only_content(self):
        f = ContainsMessageFilter("test")
        assert not f.is_match(_make_message("   "))

    def test_match_in_embed_title(self):
        embed = Embed(title="Hello World", kind=EmbedKind.RICH)
        f = ContainsMessageFilter("hello")
        assert f.is_match(_make_message("", embeds=[embed]))

    def test_match_in_embed_description(self):
        embed = Embed(description="Find me here", kind=EmbedKind.RICH)
        f = ContainsMessageFilter("find")
        assert f.is_match(_make_message("", embeds=[embed]))

    def test_match_in_embed_author(self):
        embed = Embed(author=EmbedAuthor(name="Author Name"), kind=EmbedKind.RICH)
        f = ContainsMessageFilter("author")
        assert f.is_match(_make_message("", embeds=[embed]))

    def test_match_in_embed_footer(self):
        embed = Embed(footer=EmbedFooter(text="Footer text"), kind=EmbedKind.RICH)
        f = ContainsMessageFilter("footer")
        assert f.is_match(_make_message("", embeds=[embed]))

    def test_match_in_embed_field_name(self):
        embed = Embed(
            fields=[EmbedField(name="Field Name", value="value")],
            kind=EmbedKind.RICH,
        )
        f = ContainsMessageFilter("field")
        assert f.is_match(_make_message("", embeds=[embed]))

    def test_match_in_embed_field_value(self):
        embed = Embed(
            fields=[EmbedField(name="name", value="Field Value")],
            kind=EmbedKind.RICH,
        )
        f = ContainsMessageFilter("value")
        assert f.is_match(_make_message("", embeds=[embed]))

    def test_no_match_in_embed(self):
        embed = Embed(title="Nothing here", kind=EmbedKind.RICH)
        f = ContainsMessageFilter("missing")
        assert not f.is_match(_make_message("", embeds=[embed]))


# ===================================================================
# FromMessageFilter
# ===================================================================


class TestFromMessageFilter:
    def test_match_by_name(self):
        f = FromMessageFilter("testuser")
        assert f.is_match(_make_message("hi", user=_make_user(name="testuser")))

    def test_match_by_display_name(self):
        f = FromMessageFilter("Test User")
        assert f.is_match(
            _make_message("hi", user=_make_user(display_name="Test User"))
        )

    def test_match_by_full_name_with_discriminator(self):
        f = FromMessageFilter("testuser#1234")
        assert f.is_match(
            _make_message("hi", user=_make_user(name="testuser", discriminator=1234))
        )

    def test_match_by_id(self):
        f = FromMessageFilter("1001")
        assert f.is_match(_make_message("hi", user=_make_user(uid=1001)))

    def test_case_insensitive(self):
        f = FromMessageFilter("TESTUSER")
        assert f.is_match(_make_message("hi", user=_make_user(name="testuser")))

    def test_no_match(self):
        f = FromMessageFilter("otheruser")
        assert not f.is_match(_make_message("hi", user=_make_user(name="testuser")))


# ===================================================================
# HasMessageFilter
# ===================================================================


class TestHasMessageFilter:
    def test_has_link(self):
        f = HasMessageFilter("link")
        assert f.is_match(_make_message("Check https://example.com"))

    def test_has_no_link(self):
        f = HasMessageFilter("link")
        assert not f.is_match(_make_message("No links here"))

    def test_has_embed(self):
        f = HasMessageFilter("embed")
        embed = Embed(title="Test", kind=EmbedKind.RICH)
        assert f.is_match(_make_message("", embeds=[embed]))

    def test_has_no_embed(self):
        f = HasMessageFilter("embed")
        assert not f.is_match(_make_message("No embeds"))

    def test_has_file(self):
        f = HasMessageFilter("file")
        att = Attachment(
            id=Snowflake(1),
            url="https://cdn.discordapp.com/file.zip",
            file_name="file.zip",
            file_size_bytes=100,
        )
        assert f.is_match(_make_message("", attachments=[att]))

    def test_has_no_file(self):
        f = HasMessageFilter("file")
        assert not f.is_match(_make_message("No files"))

    def test_has_video(self):
        f = HasMessageFilter("video")
        att = Attachment(
            id=Snowflake(1),
            url="https://cdn.discordapp.com/video.mp4",
            file_name="video.mp4",
            file_size_bytes=100,
        )
        assert f.is_match(_make_message("", attachments=[att]))

    def test_has_no_video(self):
        f = HasMessageFilter("video")
        att = Attachment(
            id=Snowflake(1),
            url="https://cdn.discordapp.com/image.png",
            file_name="image.png",
            file_size_bytes=100,
        )
        assert not f.is_match(_make_message("", attachments=[att]))

    def test_has_image(self):
        f = HasMessageFilter("image")
        att = Attachment(
            id=Snowflake(1),
            url="https://cdn.discordapp.com/image.png",
            file_name="image.png",
            file_size_bytes=100,
        )
        assert f.is_match(_make_message("", attachments=[att]))

    def test_has_no_image(self):
        f = HasMessageFilter("image")
        assert not f.is_match(_make_message("No images"))

    def test_has_sound(self):
        f = HasMessageFilter("sound")
        att = Attachment(
            id=Snowflake(1),
            url="https://cdn.discordapp.com/audio.mp3",
            file_name="audio.mp3",
            file_size_bytes=100,
        )
        assert f.is_match(_make_message("", attachments=[att]))

    def test_has_no_sound(self):
        f = HasMessageFilter("sound")
        assert not f.is_match(_make_message("No audio"))

    def test_has_pin(self):
        f = HasMessageFilter("pin")
        assert f.is_match(_make_message("pinned", is_pinned=True))

    def test_has_no_pin(self):
        f = HasMessageFilter("pin")
        assert not f.is_match(_make_message("not pinned", is_pinned=False))

    def test_has_invite(self):
        f = HasMessageFilter("invite")
        assert f.is_match(_make_message("Join us https://discord.gg/abc123"))

    def test_has_no_invite(self):
        f = HasMessageFilter("invite")
        assert not f.is_match(_make_message("Just a regular https://example.com"))

    def test_invalid_kind_raises(self):
        with pytest.raises(ValueError, match="Unknown 'has:' kind"):
            HasMessageFilter("invalid_kind")

    def test_from_enum(self):
        from discord_chat_exporter.core.exporting.filtering.filters import (
            MessageContentMatchKind,
        )

        f = HasMessageFilter(MessageContentMatchKind.PIN)
        assert f.is_match(_make_message("", is_pinned=True))


# ===================================================================
# MentionsMessageFilter
# ===================================================================


class TestMentionsMessageFilter:
    def test_match_by_name(self):
        mentioned = _make_user(name="target", uid=2001)
        f = MentionsMessageFilter("target")
        assert f.is_match(_make_message("hi", mentioned_users=[mentioned]))

    def test_match_by_display_name(self):
        mentioned = _make_user(display_name="Target User", uid=2001)
        f = MentionsMessageFilter("Target User")
        assert f.is_match(_make_message("hi", mentioned_users=[mentioned]))

    def test_match_by_full_name(self):
        mentioned = _make_user(name="target", discriminator=5678, uid=2001)
        f = MentionsMessageFilter("target#5678")
        assert f.is_match(_make_message("hi", mentioned_users=[mentioned]))

    def test_match_by_id(self):
        mentioned = _make_user(uid=2001)
        f = MentionsMessageFilter("2001")
        assert f.is_match(_make_message("hi", mentioned_users=[mentioned]))

    def test_case_insensitive(self):
        mentioned = _make_user(name="target", uid=2001)
        f = MentionsMessageFilter("TARGET")
        assert f.is_match(_make_message("hi", mentioned_users=[mentioned]))

    def test_no_match(self):
        f = MentionsMessageFilter("nobody")
        assert not f.is_match(_make_message("hi"))

    def test_no_match_wrong_user(self):
        mentioned = _make_user(name="other", uid=2001)
        f = MentionsMessageFilter("target")
        assert not f.is_match(_make_message("hi", mentioned_users=[mentioned]))


# ===================================================================
# ReactionMessageFilter
# ===================================================================


class TestReactionMessageFilter:
    def test_match_by_emoji_name(self):
        reaction = Reaction(
            emoji=Emoji(id=None, name="\U0001f44d", is_animated=False), count=1
        )
        f = ReactionMessageFilter("\U0001f44d")
        assert f.is_match(_make_message("", reactions=[reaction]))

    def test_match_by_custom_emoji_id(self):
        reaction = Reaction(
            emoji=Emoji(id=Snowflake(123), name="LUL", is_animated=False), count=1
        )
        f = ReactionMessageFilter("123")
        assert f.is_match(_make_message("", reactions=[reaction]))

    def test_match_by_custom_emoji_name(self):
        reaction = Reaction(
            emoji=Emoji(id=Snowflake(123), name="LUL", is_animated=False), count=1
        )
        f = ReactionMessageFilter("LUL")
        assert f.is_match(_make_message("", reactions=[reaction]))

    def test_case_insensitive(self):
        reaction = Reaction(
            emoji=Emoji(id=Snowflake(123), name="LUL", is_animated=False), count=1
        )
        f = ReactionMessageFilter("lul")
        assert f.is_match(_make_message("", reactions=[reaction]))

    def test_no_match(self):
        f = ReactionMessageFilter("LUL")
        assert not f.is_match(_make_message(""))

    def test_no_match_wrong_reaction(self):
        reaction = Reaction(
            emoji=Emoji(id=None, name="\U0001f44d", is_animated=False), count=1
        )
        f = ReactionMessageFilter("LUL")
        assert not f.is_match(_make_message("", reactions=[reaction]))


# ===================================================================
# BinaryExpressionMessageFilter
# ===================================================================


class TestBinaryExpressionAnd:
    def test_both_true(self):
        f = BinaryExpressionMessageFilter(
            ContainsMessageFilter("hello"),
            FromMessageFilter("testuser"),
            BinaryExpressionKind.AND,
        )
        msg = _make_message("hello", user=_make_user(name="testuser"))
        assert f.is_match(msg)

    def test_first_false(self):
        f = BinaryExpressionMessageFilter(
            ContainsMessageFilter("goodbye"),
            FromMessageFilter("testuser"),
            BinaryExpressionKind.AND,
        )
        msg = _make_message("hello", user=_make_user(name="testuser"))
        assert not f.is_match(msg)

    def test_second_false(self):
        f = BinaryExpressionMessageFilter(
            ContainsMessageFilter("hello"),
            FromMessageFilter("otheruser"),
            BinaryExpressionKind.AND,
        )
        msg = _make_message("hello", user=_make_user(name="testuser"))
        assert not f.is_match(msg)

    def test_both_false(self):
        f = BinaryExpressionMessageFilter(
            ContainsMessageFilter("goodbye"),
            FromMessageFilter("otheruser"),
            BinaryExpressionKind.AND,
        )
        msg = _make_message("hello", user=_make_user(name="testuser"))
        assert not f.is_match(msg)


class TestBinaryExpressionOr:
    def test_both_true(self):
        f = BinaryExpressionMessageFilter(
            ContainsMessageFilter("hello"),
            FromMessageFilter("testuser"),
            BinaryExpressionKind.OR,
        )
        msg = _make_message("hello", user=_make_user(name="testuser"))
        assert f.is_match(msg)

    def test_first_true_only(self):
        f = BinaryExpressionMessageFilter(
            ContainsMessageFilter("hello"),
            FromMessageFilter("otheruser"),
            BinaryExpressionKind.OR,
        )
        msg = _make_message("hello", user=_make_user(name="testuser"))
        assert f.is_match(msg)

    def test_second_true_only(self):
        f = BinaryExpressionMessageFilter(
            ContainsMessageFilter("goodbye"),
            FromMessageFilter("testuser"),
            BinaryExpressionKind.OR,
        )
        msg = _make_message("hello", user=_make_user(name="testuser"))
        assert f.is_match(msg)

    def test_both_false(self):
        f = BinaryExpressionMessageFilter(
            ContainsMessageFilter("goodbye"),
            FromMessageFilter("otheruser"),
            BinaryExpressionKind.OR,
        )
        msg = _make_message("hello", user=_make_user(name="testuser"))
        assert not f.is_match(msg)


# ===================================================================
# NegatedMessageFilter
# ===================================================================


class TestNegatedMessageFilter:
    def test_negate_true(self):
        f = NegatedMessageFilter(ContainsMessageFilter("hello"))
        msg = _make_message("hello world")
        assert not f.is_match(msg)

    def test_negate_false(self):
        f = NegatedMessageFilter(ContainsMessageFilter("goodbye"))
        msg = _make_message("hello world")
        assert f.is_match(msg)


# ===================================================================
# Composed Combinators
# ===================================================================


class TestComposedCombinators:
    def test_not_and(self):
        """NOT(AND(A, B)): false when both match."""
        inner = BinaryExpressionMessageFilter(
            ContainsMessageFilter("hello"),
            FromMessageFilter("testuser"),
            BinaryExpressionKind.AND,
        )
        f = NegatedMessageFilter(inner)
        msg = _make_message("hello", user=_make_user(name="testuser"))
        assert not f.is_match(msg)

    def test_not_and_partial(self):
        """NOT(AND(A, B)): true when only one matches."""
        inner = BinaryExpressionMessageFilter(
            ContainsMessageFilter("goodbye"),
            FromMessageFilter("testuser"),
            BinaryExpressionKind.AND,
        )
        f = NegatedMessageFilter(inner)
        msg = _make_message("hello", user=_make_user(name="testuser"))
        assert f.is_match(msg)

    def test_or_not_a_b(self):
        """OR(NOT(A), B): true when A is false."""
        f = BinaryExpressionMessageFilter(
            NegatedMessageFilter(ContainsMessageFilter("goodbye")),
            FromMessageFilter("otheruser"),
            BinaryExpressionKind.OR,
        )
        msg = _make_message("hello", user=_make_user(name="testuser"))
        assert f.is_match(msg)

    def test_nested_and_or_not(self):
        """AND(OR(A, B), NOT(C))"""
        or_filter = BinaryExpressionMessageFilter(
            ContainsMessageFilter("hello"),
            ContainsMessageFilter("world"),
            BinaryExpressionKind.OR,
        )
        not_filter = NegatedMessageFilter(HasMessageFilter("pin"))
        f = BinaryExpressionMessageFilter(
            or_filter, not_filter, BinaryExpressionKind.AND
        )
        msg = _make_message("hello world", is_pinned=False)
        assert f.is_match(msg)

    def test_nested_and_or_not_fails(self):
        """AND(OR(A, B), NOT(C)): fails when C is true (pinned)."""
        or_filter = BinaryExpressionMessageFilter(
            ContainsMessageFilter("hello"),
            ContainsMessageFilter("world"),
            BinaryExpressionKind.OR,
        )
        not_filter = NegatedMessageFilter(HasMessageFilter("pin"))
        f = BinaryExpressionMessageFilter(
            or_filter, not_filter, BinaryExpressionKind.AND
        )
        msg = _make_message("hello world", is_pinned=True)
        assert not f.is_match(msg)
