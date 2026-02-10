"""Comprehensive unit tests for all Discord model classes."""

import pytest
from pydantic import ValidationError

from discord_chat_exporter.core.discord.models.attachment import Attachment
from discord_chat_exporter.core.discord.models.cdn import ImageCdn
from discord_chat_exporter.core.discord.models.channel import Channel, ChannelKind
from discord_chat_exporter.core.discord.models.embed import (
    Embed,
    EmbedAuthor,
    EmbedField,
    EmbedFooter,
    EmbedImage,
    EmbedKind,
    EmbedVideo,
    SpotifyTrackEmbedProjection,
    TwitchClipEmbedProjection,
    YouTubeVideoEmbedProjection,
)
from discord_chat_exporter.core.discord.models.emoji import Emoji
from discord_chat_exporter.core.discord.models.guild import Guild
from discord_chat_exporter.core.discord.models.interaction import Interaction
from discord_chat_exporter.core.discord.models.member import Member
from discord_chat_exporter.core.discord.models.message import (
    Message,
    MessageFlags,
    MessageKind,
    MessageReference,
)
from discord_chat_exporter.core.discord.models.reaction import Reaction
from discord_chat_exporter.core.discord.models.role import Role
from discord_chat_exporter.core.discord.models.sticker import Sticker, StickerFormat
from discord_chat_exporter.core.discord.models.user import User
from discord_chat_exporter.core.discord.snowflake import Snowflake
from discord_chat_exporter.core.exporting.format import ExportFormat


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user_api_dict(**overrides):
    """Build a minimal Discord API user dict."""
    base = {
        "id": "123456",
        "username": "testuser",
        "global_name": "Test User",
        "bot": False,
        "discriminator": "0",
        "avatar": None,
    }
    base.update(overrides)
    return base


def _make_user(**overrides):
    """Build a User via API-style dict."""
    return User.model_validate(_make_user_api_dict(**overrides))


def _make_message_api_dict(**overrides):
    """Build a minimal Discord API message dict."""
    base = {
        "id": "999",
        "type": 0,
        "author": _make_user_api_dict(),
        "timestamp": "2024-01-01T00:00:00+00:00",
        "content": "hello",
    }
    base.update(overrides)
    return base


# ===========================================================================
# ImageCdn
# ===========================================================================


class TestImageCdn:
    def test_standard_emoji_url_simple(self):
        # "A" -> U+0041
        url = ImageCdn.get_standard_emoji_url("A")
        assert "41.svg" in url
        assert "cdn.jsdelivr.net" in url

    def test_standard_emoji_url_strips_variant_selector(self):
        # Heart ❤️ is U+2764 U+FE0F — FE0F should be stripped (no ZWJ)
        url = ImageCdn.get_standard_emoji_url("\u2764\ufe0f")
        assert "2764.svg" in url
        assert "fe0f" not in url

    def test_standard_emoji_url_keeps_variant_with_zwj(self):
        # Family emoji with ZWJ keeps fe0f
        emoji = "\U0001f468\u200d\u2764\ufe0f\u200d\U0001f468"
        url = ImageCdn.get_standard_emoji_url(emoji)
        assert "200d" in url
        assert "fe0f" in url

    def test_custom_emoji_url_static(self):
        url = ImageCdn.get_custom_emoji_url(Snowflake(999), is_animated=False)
        assert url == "https://cdn.discordapp.com/emojis/999.png"

    def test_custom_emoji_url_animated(self):
        url = ImageCdn.get_custom_emoji_url(Snowflake(999), is_animated=True)
        assert url == "https://cdn.discordapp.com/emojis/999.gif"

    def test_guild_icon_url_static(self):
        url = ImageCdn.get_guild_icon_url(Snowflake(1), "abc123")
        assert url == "https://cdn.discordapp.com/icons/1/abc123.png?size=512"

    def test_guild_icon_url_animated(self):
        url = ImageCdn.get_guild_icon_url(Snowflake(1), "a_abc123")
        assert url == "https://cdn.discordapp.com/icons/1/a_abc123.gif?size=512"

    def test_guild_icon_url_custom_size(self):
        url = ImageCdn.get_guild_icon_url(Snowflake(1), "abc", size=256)
        assert "size=256" in url

    def test_channel_icon_url_static(self):
        url = ImageCdn.get_channel_icon_url(Snowflake(2), "def456")
        assert "channel-icons/2/def456.png" in url

    def test_channel_icon_url_animated(self):
        url = ImageCdn.get_channel_icon_url(Snowflake(2), "a_def456")
        assert ".gif" in url

    def test_user_avatar_url_static(self):
        url = ImageCdn.get_user_avatar_url(Snowflake(3), "hash123")
        assert "avatars/3/hash123.png" in url

    def test_user_avatar_url_animated(self):
        url = ImageCdn.get_user_avatar_url(Snowflake(3), "a_hash123")
        assert ".gif" in url

    def test_fallback_user_avatar_url(self):
        url = ImageCdn.get_fallback_user_avatar_url(3)
        assert url == "https://cdn.discordapp.com/embed/avatars/3.png"

    def test_fallback_user_avatar_url_default(self):
        url = ImageCdn.get_fallback_user_avatar_url()
        assert url == "https://cdn.discordapp.com/embed/avatars/0.png"

    def test_member_avatar_url(self):
        url = ImageCdn.get_member_avatar_url(Snowflake(10), Snowflake(20), "mhash")
        assert "guilds/10/users/20/avatars/mhash.png" in url

    def test_member_avatar_url_animated(self):
        url = ImageCdn.get_member_avatar_url(Snowflake(10), Snowflake(20), "a_mhash")
        assert ".gif" in url

    def test_sticker_url_default(self):
        url = ImageCdn.get_sticker_url(Snowflake(50))
        assert url == "https://cdn.discordapp.com/stickers/50.png"

    def test_sticker_url_custom_format(self):
        url = ImageCdn.get_sticker_url(Snowflake(50), "gif")
        assert url == "https://cdn.discordapp.com/stickers/50.gif"


# ===========================================================================
# User
# ===========================================================================


class TestUser:
    def test_direct_construction(self):
        u = User(
            id=Snowflake(1),
            is_bot=False,
            discriminator=None,
            name="alice",
            display_name="Alice",
            avatar_url="https://example.com/avatar.png",
        )
        assert u.id == Snowflake(1)
        assert u.name == "alice"
        assert u.display_name == "Alice"

    def test_from_api_dict(self):
        u = User.model_validate(_make_user_api_dict(
            id="99999", username="bob", global_name="Bob B", avatar="abc123"
        ))
        assert u.id == Snowflake(99999)
        assert u.name == "bob"
        assert u.display_name == "Bob B"
        assert "abc123" in u.avatar_url

    def test_discriminator_none_when_zero(self):
        u = _make_user(discriminator="0")
        assert u.discriminator is None

    def test_discriminator_preserved_when_nonzero(self):
        u = _make_user(discriminator="1234")
        assert u.discriminator == 1234

    def test_discriminator_formatted_none(self):
        u = _make_user(discriminator="0")
        assert u.discriminator_formatted == "0000"

    def test_discriminator_formatted_nonzero(self):
        u = _make_user(discriminator="1234")
        assert u.discriminator_formatted == "1234"

    def test_discriminator_formatted_padded(self):
        u = _make_user(discriminator="7")
        assert u.discriminator_formatted == "0007"

    def test_full_name_without_discriminator(self):
        u = _make_user(discriminator="0")
        assert u.full_name == u.name

    def test_full_name_with_discriminator(self):
        u = _make_user(discriminator="1234", username="alice")
        assert u.full_name == "alice#1234"

    def test_bot_flag(self):
        u = _make_user(bot=True)
        assert u.is_bot is True

    def test_non_bot_default(self):
        u = _make_user()
        assert u.is_bot is False

    def test_avatar_fallback_when_no_hash(self):
        u = _make_user(avatar=None)
        assert "embed/avatars" in u.avatar_url

    def test_avatar_url_with_hash(self):
        u = _make_user(avatar="abc123")
        assert "avatars" in u.avatar_url
        assert "abc123" in u.avatar_url

    def test_display_name_falls_back_to_username(self):
        u = _make_user(global_name=None, username="fallback")
        assert u.display_name == "fallback"

    def test_frozen(self):
        u = _make_user()
        with pytest.raises(ValidationError):
            u.name = "changed"


# ===========================================================================
# Channel
# ===========================================================================


class TestChannelKind:
    def test_guild_text_chat_value(self):
        assert ChannelKind.GUILD_TEXT_CHAT == 0

    def test_direct_text_chat_value(self):
        assert ChannelKind.DIRECT_TEXT_CHAT == 1

    def test_guild_forum_value(self):
        assert ChannelKind.GUILD_FORUM == 15


class TestChannel:
    def _make_channel(self, kind=ChannelKind.GUILD_TEXT_CHAT, **kwargs):
        defaults = {
            "id": Snowflake(100),
            "kind": kind,
            "guild_id": Snowflake(1),
            "name": "general",
        }
        defaults.update(kwargs)
        return Channel(**defaults)

    def test_direct_construction(self):
        ch = self._make_channel()
        assert ch.id == Snowflake(100)
        assert ch.name == "general"

    def test_from_api_dict(self):
        ch = Channel.model_validate({
            "id": "200",
            "type": 0,
            "guild_id": "1",
            "name": "api-channel",
            "last_message_id": "500",
        })
        assert ch.id == Snowflake(200)
        assert ch.name == "api-channel"
        assert ch.last_message_id == Snowflake(500)

    def test_from_api_dict_dm_with_recipients(self):
        ch = Channel.model_validate({
            "id": "300",
            "type": 1,
            "recipients": [
                _make_user_api_dict(id="10", username="alice", global_name="Alice"),
                _make_user_api_dict(id="20", username="bob", global_name="Bob"),
            ],
        })
        assert ch.kind == ChannelKind.DIRECT_TEXT_CHAT
        # Name built from sorted recipients by id
        assert "Alice" in ch.name
        assert "Bob" in ch.name

    def test_from_api_dict_no_name_no_recipients(self):
        ch = Channel.model_validate({"id": "400", "type": 0})
        assert ch.name == "400"  # Falls back to ID string

    def test_is_direct_dm(self):
        assert self._make_channel(kind=ChannelKind.DIRECT_TEXT_CHAT).is_direct is True

    def test_is_direct_group_dm(self):
        assert self._make_channel(kind=ChannelKind.DIRECT_GROUP_TEXT_CHAT).is_direct is True

    def test_is_direct_guild(self):
        assert self._make_channel(kind=ChannelKind.GUILD_TEXT_CHAT).is_direct is False

    def test_is_guild(self):
        assert self._make_channel(kind=ChannelKind.GUILD_TEXT_CHAT).is_guild is True

    def test_is_guild_dm(self):
        assert self._make_channel(kind=ChannelKind.DIRECT_TEXT_CHAT).is_guild is False

    def test_is_category(self):
        assert self._make_channel(kind=ChannelKind.GUILD_CATEGORY).is_category is True

    def test_is_not_category(self):
        assert self._make_channel(kind=ChannelKind.GUILD_TEXT_CHAT).is_category is False

    def test_is_voice_voice_chat(self):
        assert self._make_channel(kind=ChannelKind.GUILD_VOICE_CHAT).is_voice is True

    def test_is_voice_stage(self):
        assert self._make_channel(kind=ChannelKind.GUILD_STAGE_VOICE).is_voice is True

    def test_is_voice_text(self):
        assert self._make_channel(kind=ChannelKind.GUILD_TEXT_CHAT).is_voice is False

    def test_is_thread_public(self):
        assert self._make_channel(kind=ChannelKind.GUILD_PUBLIC_THREAD).is_thread is True

    def test_is_thread_private(self):
        assert self._make_channel(kind=ChannelKind.GUILD_PRIVATE_THREAD).is_thread is True

    def test_is_thread_news(self):
        assert self._make_channel(kind=ChannelKind.GUILD_NEWS_THREAD).is_thread is True

    def test_is_not_thread(self):
        assert self._make_channel(kind=ChannelKind.GUILD_TEXT_CHAT).is_thread is False

    def test_is_empty_no_last_message(self):
        assert self._make_channel(last_message_id=None).is_empty is True

    def test_is_not_empty(self):
        assert self._make_channel(last_message_id=Snowflake(1)).is_empty is False

    def test_get_parents_no_parent(self):
        ch = self._make_channel()
        assert ch.get_parents() == []

    def test_get_parents_chain(self):
        root = self._make_channel(name="root", id=Snowflake(1))
        mid = self._make_channel(name="mid", id=Snowflake(2), parent=root)
        child = self._make_channel(name="child", id=Snowflake(3), parent=mid)
        parents = child.get_parents()
        assert len(parents) == 2
        assert parents[0].name == "mid"
        assert parents[1].name == "root"

    def test_try_get_root_parent(self):
        root = self._make_channel(name="root", id=Snowflake(1))
        child = self._make_channel(name="child", id=Snowflake(2), parent=root)
        assert child.try_get_root_parent().name == "root"

    def test_try_get_root_parent_none(self):
        ch = self._make_channel()
        assert ch.try_get_root_parent() is None

    def test_hierarchical_name_no_parent(self):
        ch = self._make_channel(name="general")
        assert ch.get_hierarchical_name() == "general"

    def test_hierarchical_name_with_parents(self):
        root = self._make_channel(name="Category", id=Snowflake(1))
        child = self._make_channel(name="general", id=Snowflake(2), parent=root)
        assert child.get_hierarchical_name() == "Category / general"

    def test_may_have_messages_after_true(self):
        ch = self._make_channel(last_message_id=Snowflake(100))
        assert ch.may_have_messages_after(Snowflake(50)) is True

    def test_may_have_messages_after_false(self):
        ch = self._make_channel(last_message_id=Snowflake(100))
        assert ch.may_have_messages_after(Snowflake(200)) is False

    def test_may_have_messages_after_empty(self):
        ch = self._make_channel(last_message_id=None)
        assert ch.may_have_messages_after(Snowflake(50)) is False

    def test_may_have_messages_before_true(self):
        ch = self._make_channel(id=Snowflake(10), last_message_id=Snowflake(100))
        assert ch.may_have_messages_before(Snowflake(50)) is True

    def test_may_have_messages_before_false(self):
        ch = self._make_channel(id=Snowflake(100), last_message_id=Snowflake(200))
        assert ch.may_have_messages_before(Snowflake(50)) is False

    def test_may_have_messages_before_empty(self):
        ch = self._make_channel(last_message_id=None)
        assert ch.may_have_messages_before(Snowflake(50)) is False

    def test_from_api_thread_archived(self):
        ch = Channel.model_validate({
            "id": "500",
            "type": 11,
            "guild_id": "1",
            "name": "thread",
            "thread_metadata": {"archived": True},
        })
        assert ch.is_archived is True

    def test_from_api_icon(self):
        ch = Channel.model_validate({
            "id": "600",
            "type": 3,
            "name": "group",
            "icon": "iconhash",
        })
        assert ch.icon_url is not None
        assert "iconhash" in ch.icon_url

    def test_frozen(self):
        ch = self._make_channel()
        with pytest.raises(ValidationError):
            ch.name = "changed"


# ===========================================================================
# Guild
# ===========================================================================


class TestGuild:
    def test_direct_construction(self):
        g = Guild(
            id=Snowflake(1),
            name="My Server",
            icon_url="https://example.com/icon.png",
        )
        assert g.name == "My Server"

    def test_from_api_dict_with_icon(self):
        g = Guild.model_validate({"id": "42", "name": "Test Guild", "icon": "iconhash"})
        assert g.id == Snowflake(42)
        assert "iconhash" in g.icon_url

    def test_from_api_dict_no_icon(self):
        g = Guild.model_validate({"id": "42", "name": "Test Guild", "icon": None})
        assert "embed/avatars" in g.icon_url

    def test_is_direct_true(self):
        assert Guild.DIRECT_MESSAGES.is_direct is True

    def test_is_direct_false(self):
        g = Guild(id=Snowflake(1), name="Server", icon_url="x")
        assert g.is_direct is False

    def test_direct_messages_sentinel(self):
        dm = Guild.DIRECT_MESSAGES
        assert dm.id == Snowflake.ZERO
        assert dm.name == "Direct Messages"

    def test_frozen(self):
        g = Guild(id=Snowflake(1), name="S", icon_url="x")
        with pytest.raises(ValidationError):
            g.name = "changed"


# ===========================================================================
# Role
# ===========================================================================


class TestRole:
    def test_direct_construction(self):
        r = Role(id=Snowflake(1), name="Admin", position=10, color="#ff0000")
        assert r.name == "Admin"
        assert r.color == "#ff0000"

    def test_from_api_dict_with_color(self):
        r = Role.model_validate({
            "id": "1", "name": "Mod", "position": 5, "color": 0xFF0000,
        })
        assert r.color == "#ff0000"

    def test_from_api_dict_color_zero_is_none(self):
        r = Role.model_validate({
            "id": "2", "name": "Default", "position": 0, "color": 0,
        })
        assert r.color is None

    def test_from_api_dict_no_color_key(self):
        r = Role.model_validate({
            "id": "3", "name": "No Color", "position": 1,
        })
        assert r.color is None

    def test_from_api_dict_color_formatting(self):
        r = Role.model_validate({
            "id": "4", "name": "Blue", "position": 2, "color": 0x0000FF,
        })
        assert r.color == "#0000ff"

    def test_frozen(self):
        r = Role(id=Snowflake(1), name="A", position=0)
        with pytest.raises(ValidationError):
            r.name = "changed"


# ===========================================================================
# Attachment
# ===========================================================================


class TestAttachment:
    def test_direct_construction(self):
        a = Attachment(
            id=Snowflake(1),
            url="https://cdn.discord.com/file.png",
            file_name="image.png",
            file_size_bytes=1024,
        )
        assert a.file_name == "image.png"

    def test_from_api_dict(self):
        a = Attachment.model_validate({
            "id": "1",
            "url": "https://cdn.discord.com/file.png",
            "filename": "photo.jpg",
            "description": "A photo",
            "width": 800,
            "height": 600,
            "size": 2048,
        })
        assert a.file_name == "photo.jpg"
        assert a.description == "A photo"
        assert a.width == 800
        assert a.file_size_bytes == 2048

    def test_file_extension(self):
        a = Attachment(id=Snowflake(1), url="x", file_name="test.PNG")
        assert a.file_extension == ".png"

    def test_is_image_jpg(self):
        a = Attachment(id=Snowflake(1), url="x", file_name="test.jpg")
        assert a.is_image is True

    def test_is_image_png(self):
        a = Attachment(id=Snowflake(1), url="x", file_name="test.png")
        assert a.is_image is True

    def test_is_image_gif(self):
        a = Attachment(id=Snowflake(1), url="x", file_name="test.gif")
        assert a.is_image is True

    def test_is_image_webp(self):
        a = Attachment(id=Snowflake(1), url="x", file_name="test.webp")
        assert a.is_image is True

    def test_is_image_false(self):
        a = Attachment(id=Snowflake(1), url="x", file_name="test.txt")
        assert a.is_image is False

    def test_is_video_mp4(self):
        a = Attachment(id=Snowflake(1), url="x", file_name="clip.mp4")
        assert a.is_video is True

    def test_is_video_webm(self):
        a = Attachment(id=Snowflake(1), url="x", file_name="clip.webm")
        assert a.is_video is True

    def test_is_video_false(self):
        a = Attachment(id=Snowflake(1), url="x", file_name="test.txt")
        assert a.is_video is False

    def test_is_audio_mp3(self):
        a = Attachment(id=Snowflake(1), url="x", file_name="song.mp3")
        assert a.is_audio is True

    def test_is_audio_ogg(self):
        a = Attachment(id=Snowflake(1), url="x", file_name="voice.ogg")
        assert a.is_audio is True

    def test_is_audio_false(self):
        a = Attachment(id=Snowflake(1), url="x", file_name="test.txt")
        assert a.is_audio is False

    def test_is_spoiler_true(self):
        a = Attachment(id=Snowflake(1), url="x", file_name="SPOILER_image.png")
        assert a.is_spoiler is True

    def test_is_spoiler_false(self):
        a = Attachment(id=Snowflake(1), url="x", file_name="image.png")
        assert a.is_spoiler is False

    def test_file_size_display_bytes(self):
        a = Attachment(id=Snowflake(1), url="x", file_name="f", file_size_bytes=500)
        assert a.file_size_display == "500 bytes"

    def test_file_size_display_kb(self):
        a = Attachment(id=Snowflake(1), url="x", file_name="f", file_size_bytes=2048)
        assert a.file_size_display == "2.00 KB"

    def test_file_size_display_mb(self):
        a = Attachment(id=Snowflake(1), url="x", file_name="f", file_size_bytes=5 * 1024**2)
        assert a.file_size_display == "5.00 MB"

    def test_file_size_display_gb(self):
        a = Attachment(id=Snowflake(1), url="x", file_name="f", file_size_bytes=2 * 1024**3)
        assert a.file_size_display == "2.00 GB"

    def test_frozen(self):
        a = Attachment(id=Snowflake(1), url="x", file_name="f")
        with pytest.raises(ValidationError):
            a.file_name = "changed"


# ===========================================================================
# Embed and sub-models
# ===========================================================================


class TestEmbedSubModels:
    def test_embed_author_from_api(self):
        a = EmbedAuthor.model_validate({
            "name": "Author Name",
            "url": "https://example.com",
            "proxy_icon_url": "https://proxy.example.com/icon.png",
        })
        assert a.name == "Author Name"
        assert a.icon_proxy_url == "https://proxy.example.com/icon.png"

    def test_embed_field_from_api(self):
        f = EmbedField.model_validate({
            "name": "Field", "value": "Value", "inline": True,
        })
        assert f.is_inline is True

    def test_embed_field_inline_default(self):
        f = EmbedField.model_validate({"name": "F", "value": "V"})
        assert f.is_inline is False

    def test_embed_footer_from_api(self):
        ft = EmbedFooter.model_validate({
            "text": "Footer",
            "icon_url": "https://example.com/icon.png",
            "proxy_icon_url": "https://proxy.example.com/icon.png",
        })
        assert ft.text == "Footer"
        assert ft.icon_proxy_url == "https://proxy.example.com/icon.png"

    def test_embed_image_construction(self):
        img = EmbedImage(url="https://example.com/img.png", width=100, height=200)
        assert img.width == 100

    def test_embed_video_construction(self):
        vid = EmbedVideo(url="https://example.com/vid.mp4", width=1920, height=1080)
        assert vid.height == 1080


class TestEmbed:
    def test_direct_construction(self):
        e = Embed(title="Test", kind=EmbedKind.RICH, description="Hello")
        assert e.title == "Test"
        assert e.kind == EmbedKind.RICH

    def test_from_api_dict_basic(self):
        e = Embed.model_validate({
            "type": "rich",
            "title": "Embed Title",
            "description": "Some text",
            "url": "https://example.com",
        })
        assert e.kind == EmbedKind.RICH
        assert e.title == "Embed Title"

    def test_from_api_dict_unknown_type_defaults_to_rich(self):
        e = Embed.model_validate({"type": "unknown_type"})
        assert e.kind == EmbedKind.RICH

    def test_from_api_dict_color_conversion(self):
        e = Embed.model_validate({"type": "rich", "color": 0xFF0000})
        assert e.color == "#ff0000"

    def test_from_api_dict_color_none(self):
        e = Embed.model_validate({"type": "rich"})
        assert e.color is None

    def test_from_api_dict_with_image(self):
        e = Embed.model_validate({
            "type": "rich",
            "image": {"url": "https://example.com/img.png", "width": 100, "height": 200},
        })
        assert len(e.images) == 1
        assert e.image.url == "https://example.com/img.png"

    def test_image_property_empty(self):
        e = Embed(title="x")
        assert e.image is None

    def test_image_property_first(self):
        img1 = EmbedImage(url="first")
        img2 = EmbedImage(url="second")
        e = Embed(images=[img1, img2])
        assert e.image.url == "first"

    def test_from_api_dict_with_fields(self):
        e = Embed.model_validate({
            "type": "rich",
            "fields": [
                {"name": "F1", "value": "V1", "inline": True},
                {"name": "F2", "value": "V2"},
            ],
        })
        assert len(e.fields) == 2
        assert e.fields[0].is_inline is True
        assert e.fields[1].is_inline is False

    def test_from_api_dict_with_author(self):
        e = Embed.model_validate({
            "type": "rich",
            "author": {"name": "Auth"},
        })
        assert e.author.name == "Auth"

    def test_from_api_dict_with_footer(self):
        e = Embed.model_validate({
            "type": "rich",
            "footer": {"text": "Foot"},
        })
        assert e.footer.text == "Foot"

    def test_from_api_dict_with_video(self):
        e = Embed.model_validate({
            "type": "video",
            "video": {"url": "https://example.com/video.mp4"},
        })
        assert e.kind == EmbedKind.VIDEO
        assert e.video.url == "https://example.com/video.mp4"

    def test_from_api_dict_with_thumbnail(self):
        e = Embed.model_validate({
            "type": "rich",
            "thumbnail": {"url": "https://example.com/thumb.png"},
        })
        assert e.thumbnail.url == "https://example.com/thumb.png"

    def test_embed_kind_values(self):
        assert EmbedKind.RICH.value == "rich"
        assert EmbedKind.IMAGE.value == "image"
        assert EmbedKind.VIDEO.value == "video"
        assert EmbedKind.GIFV.value == "gifv"
        assert EmbedKind.LINK.value == "link"

    def test_frozen(self):
        e = Embed(title="x")
        with pytest.raises(ValidationError):
            e.title = "changed"


class TestSpotifyTrackProjection:
    def test_resolve_spotify_track(self):
        e = Embed(kind=EmbedKind.LINK, url="https://open.spotify.com/track/abc123")
        proj = e.try_get_spotify_track()
        assert proj is not None
        assert proj.track_id == "abc123"
        assert "embed/track/abc123" in proj.url

    def test_resolve_spotify_track_with_params(self):
        e = Embed(kind=EmbedKind.LINK, url="https://open.spotify.com/track/xyz?si=foo")
        proj = e.try_get_spotify_track()
        assert proj is not None
        assert proj.track_id == "xyz"

    def test_no_resolve_wrong_kind(self):
        e = Embed(kind=EmbedKind.RICH, url="https://open.spotify.com/track/abc")
        assert e.try_get_spotify_track() is None

    def test_no_resolve_no_url(self):
        e = Embed(kind=EmbedKind.LINK)
        assert e.try_get_spotify_track() is None

    def test_no_resolve_wrong_url(self):
        e = Embed(kind=EmbedKind.LINK, url="https://example.com")
        assert e.try_get_spotify_track() is None


class TestYouTubeVideoProjection:
    def test_resolve_youtube_watch(self):
        e = Embed(kind=EmbedKind.VIDEO, url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        proj = e.try_get_youtube_video()
        assert proj is not None
        assert proj.video_id == "dQw4w9WgXcQ"
        assert "embed/dQw4w9WgXcQ" in proj.url

    def test_resolve_youtu_be(self):
        e = Embed(kind=EmbedKind.VIDEO, url="https://youtu.be/dQw4w9WgXcQ")
        proj = e.try_get_youtube_video()
        assert proj is not None
        assert proj.video_id == "dQw4w9WgXcQ"

    def test_resolve_youtube_shorts(self):
        e = Embed(kind=EmbedKind.VIDEO, url="https://www.youtube.com/shorts/dQw4w9WgXcQ")
        proj = e.try_get_youtube_video()
        assert proj is not None

    def test_resolve_youtube_embed(self):
        e = Embed(kind=EmbedKind.VIDEO, url="https://www.youtube.com/embed/dQw4w9WgXcQ")
        proj = e.try_get_youtube_video()
        assert proj is not None

    def test_no_resolve_wrong_kind(self):
        e = Embed(kind=EmbedKind.RICH, url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert e.try_get_youtube_video() is None

    def test_no_resolve_no_url(self):
        e = Embed(kind=EmbedKind.VIDEO)
        assert e.try_get_youtube_video() is None


class TestTwitchClipProjection:
    def test_resolve_clips_twitch(self):
        e = Embed(kind=EmbedKind.VIDEO, url="https://clips.twitch.tv/MyClipId")
        proj = e.try_get_twitch_clip()
        assert proj is not None
        assert proj.clip_id == "MyClipId"
        assert "clip=MyClipId" in proj.url

    def test_resolve_twitch_clip(self):
        e = Embed(kind=EmbedKind.VIDEO, url="https://www.twitch.tv/clip/AnotherClip")
        proj = e.try_get_twitch_clip()
        assert proj is not None
        assert proj.clip_id == "AnotherClip"

    def test_no_resolve_wrong_kind(self):
        e = Embed(kind=EmbedKind.RICH, url="https://clips.twitch.tv/ClipId")
        assert e.try_get_twitch_clip() is None

    def test_no_resolve_no_url(self):
        e = Embed(kind=EmbedKind.VIDEO)
        assert e.try_get_twitch_clip() is None


# ===========================================================================
# Emoji
# ===========================================================================


class TestEmoji:
    def test_custom_emoji_direct(self):
        e = Emoji(id=Snowflake(1), name="pepe", is_animated=False)
        assert e.is_custom_emoji is True
        assert e.code == "pepe"
        assert "emojis/1.png" in e.image_url

    def test_custom_emoji_animated(self):
        e = Emoji(id=Snowflake(1), name="dance", is_animated=True)
        assert "emojis/1.gif" in e.image_url

    def test_standard_emoji(self):
        e = Emoji(id=None, name="\u2764", is_animated=False)
        assert e.is_custom_emoji is False
        assert "cdn.jsdelivr.net" in e.image_url

    def test_standard_emoji_code_lookup(self):
        e = Emoji(id=None, name="\u2764", is_animated=False)
        code = e.code
        # Should return something from EMOJI_TO_CODE or the name itself
        assert isinstance(code, str)

    def test_from_api_dict_custom(self):
        e = Emoji.model_validate({"id": "999", "name": "custom_emoji", "animated": True})
        assert e.id == Snowflake(999)
        assert e.name == "custom_emoji"
        assert e.is_animated is True

    def test_from_api_dict_standard(self):
        e = Emoji.model_validate({"id": None, "name": "\U0001f600", "animated": False})
        assert e.id is None
        assert e.name == "\U0001f600"

    def test_from_api_dict_missing_name(self):
        e = Emoji.model_validate({"id": None, "name": None})
        assert e.name == "Unknown Emoji"

    def test_frozen(self):
        e = Emoji(id=None, name="x", is_animated=False)
        with pytest.raises(ValidationError):
            e.name = "changed"


# ===========================================================================
# Reaction
# ===========================================================================


class TestReaction:
    def test_direct_construction(self):
        emoji = Emoji(id=Snowflake(1), name="thumbsup", is_animated=False)
        r = Reaction(emoji=emoji, count=5)
        assert r.count == 5
        assert r.emoji.name == "thumbsup"

    def test_from_api_dict(self):
        r = Reaction.model_validate({
            "emoji": {"id": "123", "name": "fire", "animated": False},
            "count": 10,
        })
        assert r.count == 10
        assert r.emoji.id == Snowflake(123)
        assert r.emoji.name == "fire"

    def test_frozen(self):
        emoji = Emoji(id=None, name="x", is_animated=False)
        r = Reaction(emoji=emoji, count=1)
        with pytest.raises(ValidationError):
            r.count = 99


# ===========================================================================
# Sticker
# ===========================================================================


class TestStickerFormat:
    def test_values(self):
        assert StickerFormat.PNG == 1
        assert StickerFormat.APNG == 2
        assert StickerFormat.LOTTIE == 3
        assert StickerFormat.GIF == 4


class TestSticker:
    def test_direct_construction(self):
        s = Sticker(
            id=Snowflake(1), name="Wave", format=StickerFormat.PNG,
            source_url="https://cdn.discordapp.com/stickers/1.png",
        )
        assert s.name == "Wave"

    def test_is_image_png(self):
        s = Sticker(id=Snowflake(1), name="s", format=StickerFormat.PNG, source_url="x")
        assert s.is_image is True

    def test_is_image_apng(self):
        s = Sticker(id=Snowflake(1), name="s", format=StickerFormat.APNG, source_url="x")
        assert s.is_image is True

    def test_is_image_gif(self):
        s = Sticker(id=Snowflake(1), name="s", format=StickerFormat.GIF, source_url="x")
        assert s.is_image is True

    def test_is_image_lottie_false(self):
        s = Sticker(id=Snowflake(1), name="s", format=StickerFormat.LOTTIE, source_url="x")
        assert s.is_image is False

    def test_from_api_dict_png(self):
        s = Sticker.model_validate({"id": "10", "name": "Wave", "format_type": 1})
        assert s.format == StickerFormat.PNG
        assert s.source_url.endswith(".png")

    def test_from_api_dict_lottie(self):
        s = Sticker.model_validate({"id": "11", "name": "Anim", "format_type": 3})
        assert s.format == StickerFormat.LOTTIE
        assert s.source_url.endswith(".json")

    def test_from_api_dict_gif(self):
        s = Sticker.model_validate({"id": "12", "name": "GifS", "format_type": 4})
        assert s.format == StickerFormat.GIF
        assert s.source_url.endswith(".gif")

    def test_frozen(self):
        s = Sticker(id=Snowflake(1), name="s", format=StickerFormat.PNG, source_url="x")
        with pytest.raises(ValidationError):
            s.name = "changed"


# ===========================================================================
# Interaction
# ===========================================================================


class TestInteraction:
    def test_direct_construction(self):
        u = User(
            id=Snowflake(1), name="alice", display_name="Alice",
            avatar_url="https://example.com/a.png",
        )
        i = Interaction(id=Snowflake(100), name="slash_cmd", user=u)
        assert i.name == "slash_cmd"
        assert i.user.name == "alice"

    def test_from_api_dict(self):
        i = Interaction.model_validate({
            "id": "200",
            "name": "test_command",
            "user": _make_user_api_dict(id="50", username="bob"),
        })
        assert i.id == Snowflake(200)
        assert i.name == "test_command"
        assert i.user.id == Snowflake(50)

    def test_frozen(self):
        u = User(
            id=Snowflake(1), name="a", display_name="A", avatar_url="x",
        )
        i = Interaction(id=Snowflake(1), name="cmd", user=u)
        with pytest.raises(ValidationError):
            i.name = "changed"


# ===========================================================================
# Member
# ===========================================================================


class TestMember:
    def test_direct_construction(self):
        u = User(
            id=Snowflake(1), name="alice", display_name="Alice",
            avatar_url="https://example.com/a.png",
        )
        m = Member(user=u, display_name="Nickname", role_ids=[Snowflake(10)])
        assert m.id == Snowflake(1)
        assert m.display_name == "Nickname"
        assert len(m.role_ids) == 1

    def test_id_delegates_to_user(self):
        u = User(
            id=Snowflake(42), name="x", display_name="X", avatar_url="x",
        )
        m = Member(user=u)
        assert m.id == Snowflake(42)

    def test_create_fallback(self):
        u = User(
            id=Snowflake(1), name="alice", display_name="Alice",
            avatar_url="https://example.com/a.png",
        )
        m = Member.create_fallback(u)
        assert m.user == u
        assert m.display_name is None
        assert m.avatar_url is None
        assert m.role_ids == []

    def test_from_api_dict(self):
        m = Member.model_validate({
            "user": _make_user_api_dict(id="123", username="bob"),
            "nick": "Bobby",
            "roles": ["10", "20"],
        })
        assert m.user.id == Snowflake(123)
        assert m.display_name == "Bobby"
        assert Snowflake(10) in m.role_ids
        assert Snowflake(20) in m.role_ids

    def test_from_api_dict_blank_nick(self):
        m = Member.model_validate({
            "user": _make_user_api_dict(),
            "nick": "  ",
            "roles": [],
        })
        assert m.display_name is None

    def test_from_api_dict_no_nick(self):
        m = Member.model_validate({
            "user": _make_user_api_dict(),
            "roles": [],
        })
        assert m.display_name is None

    def test_from_api_dict_with_guild_avatar(self):
        m = Member.model_validate({
            "user": _make_user_api_dict(id="50"),
            "nick": None,
            "roles": [],
            "avatar": "guild_avatar_hash",
            "_guild_id": Snowflake(999),
        })
        assert m.avatar_url is not None
        assert "guild_avatar_hash" in m.avatar_url

    def test_from_api_dict_no_guild_avatar(self):
        m = Member.model_validate({
            "user": _make_user_api_dict(),
            "roles": [],
        })
        assert m.avatar_url is None

    def test_frozen(self):
        u = User(id=Snowflake(1), name="a", display_name="A", avatar_url="x")
        m = Member(user=u)
        with pytest.raises(ValidationError):
            m.display_name = "changed"


# ===========================================================================
# MessageReference
# ===========================================================================


class TestMessageReference:
    def test_direct_construction(self):
        ref = MessageReference(
            message_id=Snowflake(1), channel_id=Snowflake(2), guild_id=Snowflake(3),
        )
        assert ref.message_id == Snowflake(1)

    def test_from_api_dict(self):
        ref = MessageReference.model_validate({
            "message_id": "100", "channel_id": "200", "guild_id": "300",
        })
        assert ref.message_id == Snowflake(100)
        assert ref.channel_id == Snowflake(200)
        assert ref.guild_id == Snowflake(300)

    def test_from_api_dict_partial(self):
        ref = MessageReference.model_validate({"message_id": "100"})
        assert ref.message_id == Snowflake(100)
        assert ref.channel_id is None
        assert ref.guild_id is None

    def test_frozen(self):
        ref = MessageReference()
        with pytest.raises(ValidationError):
            ref.message_id = Snowflake(1)


# ===========================================================================
# MessageKind and MessageFlags
# ===========================================================================


class TestMessageKindAndFlags:
    def test_message_kind_values(self):
        assert MessageKind.DEFAULT == 0
        assert MessageKind.RECIPIENT_ADD == 1
        assert MessageKind.REPLY == 19
        assert MessageKind.THREAD_CREATED == 18

    def test_message_flags_none(self):
        assert MessageFlags.NONE == 0

    def test_message_flags_combinations(self):
        combined = MessageFlags.CROSS_POSTED | MessageFlags.URGENT
        assert MessageFlags.CROSS_POSTED in combined
        assert MessageFlags.URGENT in combined
        assert MessageFlags.EPHEMERAL not in combined

    def test_message_flags_values(self):
        assert MessageFlags.CROSS_POSTED == 1
        assert MessageFlags.SUPPRESS_EMBEDS == 4
        assert MessageFlags.HAS_THREAD == 32


# ===========================================================================
# Message
# ===========================================================================


class TestMessage:
    def test_from_api_dict_basic(self):
        m = Message.model_validate(_make_message_api_dict())
        assert m.id == Snowflake(999)
        assert m.kind == MessageKind.DEFAULT
        assert m.content == "hello"

    def test_is_system_notification_default(self):
        m = Message.model_validate(_make_message_api_dict(type=0))
        assert m.is_system_notification is False

    def test_is_system_notification_recipient_add(self):
        m = Message.model_validate(_make_message_api_dict(type=1))
        assert m.is_system_notification is True

    def test_is_system_notification_guild_member_join(self):
        m = Message.model_validate(_make_message_api_dict(type=7))
        assert m.is_system_notification is True

    def test_is_system_notification_thread_created(self):
        m = Message.model_validate(_make_message_api_dict(type=18))
        assert m.is_system_notification is True

    def test_is_reply_true(self):
        m = Message.model_validate(_make_message_api_dict(type=19))
        assert m.is_reply is True

    def test_is_reply_false(self):
        m = Message.model_validate(_make_message_api_dict(type=0))
        assert m.is_reply is False

    def test_is_reply_like_with_reply(self):
        m = Message.model_validate(_make_message_api_dict(type=19))
        assert m.is_reply_like is True

    def test_is_reply_like_with_interaction(self):
        m = Message.model_validate(_make_message_api_dict(
            interaction={
                "id": "1",
                "name": "cmd",
                "user": _make_user_api_dict(id="50"),
            },
        ))
        assert m.is_reply_like is True

    def test_is_reply_like_false(self):
        m = Message.model_validate(_make_message_api_dict())
        assert m.is_reply_like is False

    def test_is_empty_true(self):
        m = Message.model_validate(_make_message_api_dict(content=""))
        assert m.is_empty is True

    def test_is_empty_whitespace_only(self):
        m = Message.model_validate(_make_message_api_dict(content="   "))
        assert m.is_empty is True

    def test_is_empty_false_with_content(self):
        m = Message.model_validate(_make_message_api_dict(content="hello"))
        assert m.is_empty is False

    def test_is_empty_false_with_attachment(self):
        m = Message.model_validate(_make_message_api_dict(
            content="",
            attachments=[{
                "id": "1", "url": "https://x.com/f.png", "filename": "f.png", "size": 100,
            }],
        ))
        assert m.is_empty is False

    def test_is_empty_false_with_embed(self):
        m = Message.model_validate(_make_message_api_dict(
            content="",
            embeds=[{"type": "rich", "title": "Embed"}],
        ))
        assert m.is_empty is False

    def test_is_empty_false_with_sticker(self):
        m = Message.model_validate(_make_message_api_dict(
            content="",
            sticker_items=[{"id": "1", "name": "Sticker", "format_type": 1}],
        ))
        assert m.is_empty is False

    def test_get_referenced_users_author_only(self):
        m = Message.model_validate(_make_message_api_dict())
        users = list(m.get_referenced_users())
        assert len(users) == 1
        assert users[0] == m.author

    def test_get_referenced_users_with_mentions(self):
        m = Message.model_validate(_make_message_api_dict(
            mentions=[_make_user_api_dict(id="50", username="mentioned")],
        ))
        users = list(m.get_referenced_users())
        assert len(users) == 2

    def test_get_referenced_users_with_referenced_message(self):
        m = Message.model_validate(_make_message_api_dict(
            type=19,
            referenced_message=_make_message_api_dict(
                id="888",
                author=_make_user_api_dict(id="77", username="refauthor"),
            ),
        ))
        users = list(m.get_referenced_users())
        assert any(u.id == Snowflake(77) for u in users)

    def test_get_referenced_users_with_interaction(self):
        m = Message.model_validate(_make_message_api_dict(
            interaction={
                "id": "1",
                "name": "cmd",
                "user": _make_user_api_dict(id="88", username="interactor"),
            },
        ))
        users = list(m.get_referenced_users())
        assert any(u.id == Snowflake(88) for u in users)

    def test_from_api_with_flags(self):
        m = Message.model_validate(_make_message_api_dict(flags=4))
        assert MessageFlags.SUPPRESS_EMBEDS in m.flags

    def test_from_api_with_pinned(self):
        m = Message.model_validate(_make_message_api_dict(pinned=True))
        assert m.is_pinned is True

    def test_from_api_with_edited_timestamp(self):
        m = Message.model_validate(_make_message_api_dict(
            edited_timestamp="2024-06-01T12:00:00+00:00",
        ))
        assert m.edited_timestamp is not None

    def test_from_api_with_reactions(self):
        m = Message.model_validate(_make_message_api_dict(
            reactions=[{"emoji": {"id": None, "name": "\u2764"}, "count": 3}],
        ))
        assert len(m.reactions) == 1
        assert m.reactions[0].count == 3

    def test_from_api_with_message_reference(self):
        m = Message.model_validate(_make_message_api_dict(
            type=19,
            message_reference={"message_id": "500", "channel_id": "600"},
        ))
        assert m.reference is not None
        assert m.reference.message_id == Snowflake(500)

    def test_frozen(self):
        m = Message.model_validate(_make_message_api_dict())
        with pytest.raises(ValidationError):
            m.content = "changed"


class TestMessageNormalizeEmbeds:
    def test_no_embeds(self):
        result = Message._normalize_embeds([])
        assert result == []

    def test_single_embed_unchanged(self):
        e = Embed(title="Solo")
        result = Message._normalize_embeds([e])
        assert result == [e]

    def test_non_twitter_embeds_unchanged(self):
        e1 = Embed(title="A", url="https://example.com")
        e2 = Embed(title="B", url="https://other.com")
        result = Message._normalize_embeds([e1, e2])
        assert len(result) == 2

    def test_twitter_embeds_merged(self):
        img1 = EmbedImage(url="https://pbs.twimg.com/1.jpg")
        img2 = EmbedImage(url="https://pbs.twimg.com/2.jpg")
        main = Embed(
            kind=EmbedKind.RICH,
            title="Tweet",
            url="https://twitter.com/user/status/123",
            description="Text",
            images=[img1],
            author=EmbedAuthor(name="User"),
            color="#1da1f2",
        )
        trailing = Embed(
            kind=EmbedKind.RICH,
            url="https://twitter.com/user/status/123",
            images=[img2],
        )
        result = Message._normalize_embeds([main, trailing])
        assert len(result) == 1
        assert len(result[0].images) == 2

    def test_twitter_embeds_not_merged_different_url(self):
        img1 = EmbedImage(url="https://pbs.twimg.com/1.jpg")
        img2 = EmbedImage(url="https://pbs.twimg.com/2.jpg")
        e1 = Embed(
            kind=EmbedKind.RICH,
            url="https://twitter.com/user/status/123",
            images=[img1],
            author=EmbedAuthor(name="User"),
        )
        e2 = Embed(
            kind=EmbedKind.RICH,
            url="https://twitter.com/other/status/456",
            images=[img2],
        )
        result = Message._normalize_embeds([e1, e2])
        assert len(result) == 2


# ===========================================================================
# ExportFormat
# ===========================================================================


class TestExportFormat:
    def test_file_extension_txt(self):
        assert ExportFormat.PLAIN_TEXT.file_extension == "txt"

    def test_file_extension_html_dark(self):
        assert ExportFormat.HTML_DARK.file_extension == "html"

    def test_file_extension_html_light(self):
        assert ExportFormat.HTML_LIGHT.file_extension == "html"

    def test_file_extension_csv(self):
        assert ExportFormat.CSV.file_extension == "csv"

    def test_file_extension_json(self):
        assert ExportFormat.JSON.file_extension == "json"

    def test_display_name_txt(self):
        assert ExportFormat.PLAIN_TEXT.display_name == "TXT"

    def test_display_name_html_dark(self):
        assert ExportFormat.HTML_DARK.display_name == "HTML (Dark)"

    def test_display_name_csv(self):
        assert ExportFormat.CSV.display_name == "CSV"

    def test_is_html_dark(self):
        assert ExportFormat.HTML_DARK.is_html is True

    def test_is_html_light(self):
        assert ExportFormat.HTML_LIGHT.is_html is True

    def test_is_html_txt(self):
        assert ExportFormat.PLAIN_TEXT.is_html is False

    def test_is_html_csv(self):
        assert ExportFormat.CSV.is_html is False

    def test_is_html_json(self):
        assert ExportFormat.JSON.is_html is False
