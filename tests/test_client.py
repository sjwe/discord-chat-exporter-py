"""Tests for Discord client, HTTP utilities, and asset downloader."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from tenacity import RetryCallState

from discord_chat_exporter.core.discord.client import (
    DiscordClient,
    Invite,
    TokenKind,
)
from discord_chat_exporter.core.discord.models.guild import Guild
from discord_chat_exporter.core.discord.snowflake import Snowflake
from discord_chat_exporter.core.exceptions import DiscordChatExporterError
from discord_chat_exporter.core.exporting.asset_downloader import (
    ExportAssetDownloader,
    _is_url_allowed,
)
from discord_chat_exporter.core.utils.http import (
    _compute_retry_wait,
    _is_retryable_exception,
    _is_retryable_response,
    _is_retryable_status,
    create_async_client,
)


# ===========================================================================
# Invite
# ===========================================================================


class TestInviteTryGetCodeFromUrl:
    def test_valid_invite_url(self):
        assert Invite.try_get_code_from_url("https://discord.gg/abc123") == "abc123"

    def test_trailing_slash(self):
        assert Invite.try_get_code_from_url("https://discord.gg/abc123/") == "abc123"

    def test_http_variant(self):
        assert Invite.try_get_code_from_url("http://discord.gg/abc123") == "abc123"

    def test_not_invite_url(self):
        assert Invite.try_get_code_from_url("https://example.com") is None

    def test_not_discord_gg(self):
        assert Invite.try_get_code_from_url("https://discord.com/invite/abc") is None

    def test_empty_string(self):
        assert Invite.try_get_code_from_url("") is None

    def test_just_domain(self):
        assert Invite.try_get_code_from_url("https://discord.gg/") is None

    def test_code_with_underscores(self):
        assert Invite.try_get_code_from_url("https://discord.gg/my_server") == "my_server"

    def test_code_with_numbers(self):
        assert Invite.try_get_code_from_url("https://discord.gg/12345") == "12345"


class TestInviteInit:
    def test_basic_construction(self):
        invite = Invite(code="abc123")
        assert invite.code == "abc123"
        assert invite.guild is None
        assert invite.channel is None

    def test_with_guild(self):
        guild = Guild.DIRECT_MESSAGES
        invite = Invite(code="abc", guild=guild)
        assert invite.guild is guild


# ===========================================================================
# TokenKind
# ===========================================================================


class TestTokenKind:
    def test_user_value(self):
        assert TokenKind.USER.value == "user"

    def test_bot_value(self):
        assert TokenKind.BOT.value == "bot"

    def test_enum_members(self):
        assert set(TokenKind) == {TokenKind.USER, TokenKind.BOT}


# ===========================================================================
# HTTP Utils — _is_retryable_status
# ===========================================================================


class TestIsRetryableStatus:
    def test_429_retryable(self):
        assert _is_retryable_status(429) is True

    def test_408_retryable(self):
        assert _is_retryable_status(408) is True

    def test_500_retryable(self):
        assert _is_retryable_status(500) is True

    def test_502_retryable(self):
        assert _is_retryable_status(502) is True

    def test_503_retryable(self):
        assert _is_retryable_status(503) is True

    def test_504_retryable(self):
        assert _is_retryable_status(504) is True

    def test_200_not_retryable(self):
        assert _is_retryable_status(200) is False

    def test_401_not_retryable(self):
        assert _is_retryable_status(401) is False

    def test_403_not_retryable(self):
        assert _is_retryable_status(403) is False

    def test_404_not_retryable(self):
        assert _is_retryable_status(404) is False

    def test_201_not_retryable(self):
        assert _is_retryable_status(201) is False

    def test_499_not_retryable(self):
        assert _is_retryable_status(499) is False


# ===========================================================================
# HTTP Utils — _is_retryable_response
# ===========================================================================


def _make_mock_response(status_code: int, headers: dict | None = None) -> httpx.Response:
    """Build a minimal httpx.Response with a given status code."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.headers = httpx.Headers(headers or {})
    return resp


class TestIsRetryableResponse:
    def test_429_retryable(self):
        assert _is_retryable_response(_make_mock_response(429)) is True

    def test_500_retryable(self):
        assert _is_retryable_response(_make_mock_response(500)) is True

    def test_200_not_retryable(self):
        assert _is_retryable_response(_make_mock_response(200)) is False

    def test_401_not_retryable(self):
        assert _is_retryable_response(_make_mock_response(401)) is False

    def test_404_not_retryable(self):
        assert _is_retryable_response(_make_mock_response(404)) is False


# ===========================================================================
# HTTP Utils — _is_retryable_exception
# ===========================================================================


class TestIsRetryableException:
    def test_timeout_exception(self):
        exc = httpx.TimeoutException("timed out")
        assert _is_retryable_exception(exc) is True

    def test_network_error(self):
        exc = httpx.NetworkError("connection reset")
        assert _is_retryable_exception(exc) is True

    def test_connect_timeout(self):
        exc = httpx.ConnectTimeout("connect timed out")
        assert _is_retryable_exception(exc) is True

    def test_read_timeout(self):
        exc = httpx.ReadTimeout("read timed out")
        assert _is_retryable_exception(exc) is True

    def test_http_status_error_retryable(self):
        request = httpx.Request("GET", "https://example.com")
        response = httpx.Response(500, request=request)
        exc = httpx.HTTPStatusError("error", request=request, response=response)
        assert _is_retryable_exception(exc) is True

    def test_http_status_error_not_retryable(self):
        request = httpx.Request("GET", "https://example.com")
        response = httpx.Response(401, request=request)
        exc = httpx.HTTPStatusError("error", request=request, response=response)
        assert _is_retryable_exception(exc) is False

    def test_value_error_not_retryable(self):
        assert _is_retryable_exception(ValueError("bad")) is False

    def test_runtime_error_not_retryable(self):
        assert _is_retryable_exception(RuntimeError("fail")) is False

    def test_keyboard_interrupt_not_retryable(self):
        assert _is_retryable_exception(KeyboardInterrupt()) is False


# ===========================================================================
# HTTP Utils — _compute_retry_wait
# ===========================================================================


def _make_retry_state(
    attempt: int = 1,
    response: httpx.Response | None = None,
    exception: BaseException | None = None,
) -> RetryCallState:
    """Build a mock RetryCallState for testing _compute_retry_wait."""
    state = MagicMock(spec=RetryCallState)
    state.attempt_number = attempt

    if response is not None:
        outcome = MagicMock()
        outcome.failed = False
        outcome.result.return_value = response
        state.outcome = outcome
    elif exception is not None:
        outcome = MagicMock()
        outcome.failed = True
        outcome.exception.return_value = exception
        state.outcome = outcome
    else:
        state.outcome = None

    return state


class TestComputeRetryWait:
    def test_retry_after_header(self):
        resp = _make_mock_response(429, {"Retry-After": "5"})
        state = _make_retry_state(attempt=1, response=resp)
        assert _compute_retry_wait(state) == 6.0  # 5 + 1 buffer

    def test_retry_after_header_float(self):
        resp = _make_mock_response(429, {"Retry-After": "2.5"})
        state = _make_retry_state(attempt=1, response=resp)
        assert _compute_retry_wait(state) == 3.5  # 2.5 + 1 buffer

    def test_no_retry_after_attempt_1(self):
        resp = _make_mock_response(500)
        state = _make_retry_state(attempt=1, response=resp)
        # No Retry-After header → exponential: 2^1 + 1 = 3.0
        assert _compute_retry_wait(state) == 3.0

    def test_no_retry_after_attempt_2(self):
        resp = _make_mock_response(500)
        state = _make_retry_state(attempt=2, response=resp)
        # 2^2 + 1 = 5.0
        assert _compute_retry_wait(state) == 5.0

    def test_no_retry_after_attempt_3(self):
        resp = _make_mock_response(500)
        state = _make_retry_state(attempt=3, response=resp)
        # 2^3 + 1 = 9.0
        assert _compute_retry_wait(state) == 9.0

    def test_exception_outcome(self):
        exc = httpx.TimeoutException("timed out")
        state = _make_retry_state(attempt=2, exception=exc)
        # Failed outcome → exponential backoff: 2^2 + 1 = 5.0
        assert _compute_retry_wait(state) == 5.0

    def test_no_outcome(self):
        state = _make_retry_state(attempt=1)
        # outcome is None → exponential backoff: 2^1 + 1 = 3.0
        assert _compute_retry_wait(state) == 3.0

    def test_invalid_retry_after(self):
        resp = _make_mock_response(429, {"Retry-After": "not-a-number"})
        state = _make_retry_state(attempt=1, response=resp)
        # Invalid Retry-After falls back to exponential: 2^1 + 1 = 3.0
        assert _compute_retry_wait(state) == 3.0


# ===========================================================================
# HTTP Utils — create_async_client
# ===========================================================================


class TestCreateAsyncClient:
    def test_returns_async_client(self):
        with patch("discord_chat_exporter.core.utils.http.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = create_async_client()
            mock_cls.assert_called_once()

    def test_calls_with_http2(self):
        with patch("discord_chat_exporter.core.utils.http.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            create_async_client()
            kwargs = mock_cls.call_args[1]
            assert kwargs["http2"] is True

    def test_timeout_configured(self):
        with patch("discord_chat_exporter.core.utils.http.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            create_async_client()
            kwargs = mock_cls.call_args[1]
            assert kwargs["timeout"] == httpx.Timeout(30.0)

    def test_follow_redirects(self):
        with patch("discord_chat_exporter.core.utils.http.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            create_async_client()
            kwargs = mock_cls.call_args[1]
            assert kwargs["follow_redirects"] is True

    def test_custom_kwargs_forwarded(self):
        """Extra kwargs are passed through to AsyncClient."""
        with patch("discord_chat_exporter.core.utils.http.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            create_async_client(base_url="https://example.com")
            kwargs = mock_cls.call_args[1]
            assert kwargs["base_url"] == "https://example.com"


# ===========================================================================
# ExportAssetDownloader — _is_url_allowed
# ===========================================================================


class TestIsUrlAllowed:
    def test_cdn_discordapp(self):
        assert _is_url_allowed("https://cdn.discordapp.com/attachments/123/456/img.png") is True

    def test_media_discordapp(self):
        assert _is_url_allowed("https://media.discordapp.net/attachments/123/img.png") is True

    def test_images_ext_1(self):
        assert _is_url_allowed("https://images-ext-1.discordapp.net/img.png") is True

    def test_images_ext_2(self):
        assert _is_url_allowed("https://images-ext-2.discordapp.net/img.png") is True

    def test_cdnjs_cloudflare(self):
        assert _is_url_allowed("https://cdnjs.cloudflare.com/script.js") is True

    def test_cdn_jsdelivr(self):
        assert _is_url_allowed("https://cdn.jsdelivr.net/npm/lib@1.0/dist/lib.js") is True

    def test_evil_domain(self):
        assert _is_url_allowed("https://evil.com/malware.exe") is False

    def test_example_domain(self):
        assert _is_url_allowed("https://example.com/img.png") is False

    def test_empty_url(self):
        assert _is_url_allowed("") is False

    def test_malformed_url(self):
        assert _is_url_allowed("not-a-url") is False

    def test_subdomain_not_matched(self):
        assert _is_url_allowed("https://evil.cdn.discordapp.com/img.png") is False

    def test_case_insensitive(self):
        assert _is_url_allowed("https://CDN.DISCORDAPP.COM/img.png") is True


# ===========================================================================
# ExportAssetDownloader — _normalize_url
# ===========================================================================


class TestNormalizeUrl:
    def test_strips_query_params(self):
        result = ExportAssetDownloader._normalize_url(
            "https://cdn.discordapp.com/img.png?size=512&format=webp"
        )
        assert result == "https://cdn.discordapp.com/img.png"

    def test_strips_fragment(self):
        result = ExportAssetDownloader._normalize_url(
            "https://cdn.discordapp.com/img.png#section"
        )
        assert result == "https://cdn.discordapp.com/img.png"

    def test_strips_both(self):
        result = ExportAssetDownloader._normalize_url(
            "https://cdn.discordapp.com/img.png?size=512#top"
        )
        assert result == "https://cdn.discordapp.com/img.png"

    def test_no_params_unchanged(self):
        url = "https://cdn.discordapp.com/img.png"
        result = ExportAssetDownloader._normalize_url(url)
        assert result == url


# ===========================================================================
# ExportAssetDownloader — _get_file_name_from_url
# ===========================================================================


class TestGetFileNameFromUrl:
    def test_normal_filename(self):
        result = ExportAssetDownloader._get_file_name_from_url(
            "https://cdn.discordapp.com/path/image.png"
        )
        assert result == "image.png"

    def test_nested_path(self):
        result = ExportAssetDownloader._get_file_name_from_url(
            "https://cdn.discordapp.com/a/b/c/file.txt"
        )
        assert result == "file.txt"

    def test_empty_path(self):
        result = ExportAssetDownloader._get_file_name_from_url("https://cdn.discordapp.com/")
        assert result == "unknown"

    def test_trailing_slash(self):
        result = ExportAssetDownloader._get_file_name_from_url(
            "https://cdn.discordapp.com/dir/"
        )
        # Path.name of "dir" after rstrip("/") is "dir"
        assert result == "dir"

    def test_special_chars_sanitized(self):
        result = ExportAssetDownloader._get_file_name_from_url(
            "https://cdn.discordapp.com/path/file<name>.png"
        )
        assert "<" not in result
        assert ">" not in result

    def test_no_path(self):
        result = ExportAssetDownloader._get_file_name_from_url("https://cdn.discordapp.com")
        assert result == "unknown"


# ===========================================================================
# ExportAssetDownloader — _get_file_path
# ===========================================================================


class TestGetFilePath:
    def test_includes_hash(self):
        downloader = ExportAssetDownloader(base_dir="/tmp/assets")
        path = downloader._get_file_path("https://cdn.discordapp.com/img.png")
        # Should contain a hash segment
        filename = os.path.basename(path)
        assert "-" in filename  # hash separator

    def test_preserves_extension(self):
        downloader = ExportAssetDownloader(base_dir="/tmp/assets")
        path = downloader._get_file_path("https://cdn.discordapp.com/photo.jpg")
        assert path.endswith(".jpg")

    def test_uses_base_dir(self):
        downloader = ExportAssetDownloader(base_dir="/my/export/dir")
        path = downloader._get_file_path("https://cdn.discordapp.com/img.png")
        assert path.startswith("/my/export/dir/")

    def test_same_url_same_path(self):
        downloader = ExportAssetDownloader(base_dir="/tmp/assets")
        path1 = downloader._get_file_path("https://cdn.discordapp.com/img.png")
        path2 = downloader._get_file_path("https://cdn.discordapp.com/img.png")
        assert path1 == path2

    def test_different_urls_different_paths(self):
        downloader = ExportAssetDownloader(base_dir="/tmp/assets")
        path1 = downloader._get_file_path("https://cdn.discordapp.com/img1.png")
        path2 = downloader._get_file_path("https://cdn.discordapp.com/img2.png")
        assert path1 != path2

    def test_query_params_ignored_for_hash(self):
        downloader = ExportAssetDownloader(base_dir="/tmp/assets")
        path1 = downloader._get_file_path("https://cdn.discordapp.com/img.png?size=512")
        path2 = downloader._get_file_path("https://cdn.discordapp.com/img.png?size=1024")
        assert path1 == path2  # same hash since query is stripped


# ===========================================================================
# ExportAssetDownloader — download
# ===========================================================================


class TestExportAssetDownloaderDownload:
    async def test_disallowed_domain_returns_original_url(self):
        downloader = ExportAssetDownloader(base_dir="/tmp/assets")
        result = await downloader.download("https://evil.com/malware.exe")
        assert result == "https://evil.com/malware.exe"

    async def test_allowed_domain_reuse_existing(self):
        downloader = ExportAssetDownloader(base_dir="/tmp/assets", should_reuse=True)
        url = "https://cdn.discordapp.com/attachments/123/456/img.png"
        expected_path = downloader._get_file_path(url)

        with patch("os.path.exists", return_value=True):
            result = await downloader.download(url)

        assert result == expected_path

    async def test_no_reuse_when_disabled(self):
        """When should_reuse=False, even existing files should be re-downloaded."""
        downloader = ExportAssetDownloader(base_dir="/tmp/assets", should_reuse=False)
        url = "https://cdn.discordapp.com/attachments/123/456/img.png"

        # Build an async iterator for streaming chunks
        async def aiter_bytes(chunk_size=8192):
            yield b"data"

        # Mock the HTTP client with stream context manager
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.aiter_bytes = aiter_bytes

        mock_client = AsyncMock()
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)
        downloader._external_client = mock_client

        with (
            patch(
                "discord_chat_exporter.core.exporting.asset_downloader.os.path.exists",
                return_value=False,
            ),
            patch("discord_chat_exporter.core.exporting.asset_downloader.os.makedirs"),
            patch("builtins.open", MagicMock()),
        ):
            result = await downloader.download(url)

        assert result != url  # Should return file path, not original URL


# ===========================================================================
# DiscordClient — _auth_header
# ===========================================================================


class TestAuthHeader:
    def test_bot_token(self):
        client = DiscordClient(token="mytoken123")
        assert client._auth_header(TokenKind.BOT) == "Bot mytoken123"

    def test_user_token(self):
        client = DiscordClient(token="mytoken123")
        assert client._auth_header(TokenKind.USER) == "mytoken123"

    def test_bot_prefix(self):
        client = DiscordClient(token="abc")
        result = client._auth_header(TokenKind.BOT)
        assert result.startswith("Bot ")

    def test_user_no_prefix(self):
        client = DiscordClient(token="abc")
        result = client._auth_header(TokenKind.USER)
        assert not result.startswith("Bot ")


# ===========================================================================
# DiscordClient — _resolve_token_kind
# ===========================================================================


class TestResolveTokenKind:
    async def test_bot_auth_succeeds(self):
        client = DiscordClient(token="bot-token")
        mock_resp = _make_mock_response(200)
        with patch.object(client, "_raw_request", new_callable=AsyncMock, return_value=mock_resp):
            result = await client._resolve_token_kind()
        assert result == TokenKind.BOT

    async def test_bot_fails_user_succeeds(self):
        client = DiscordClient(token="user-token")
        bot_resp = _make_mock_response(401)
        user_resp = _make_mock_response(200)

        call_count = 0

        async def side_effect(url, token_kind):
            nonlocal call_count
            call_count += 1
            if token_kind == TokenKind.BOT:
                return bot_resp
            return user_resp

        with patch.object(client, "_raw_request", side_effect=side_effect):
            result = await client._resolve_token_kind()
        assert result == TokenKind.USER

    async def test_both_fail_raises(self):
        client = DiscordClient(token="bad-token")
        mock_resp = _make_mock_response(401)
        with patch.object(client, "_raw_request", new_callable=AsyncMock, return_value=mock_resp):
            with pytest.raises(DiscordChatExporterError, match="Authentication token is invalid"):
                await client._resolve_token_kind()

    async def test_caches_result(self):
        client = DiscordClient(token="bot-token")
        mock_resp = _make_mock_response(200)
        with patch.object(client, "_raw_request", new_callable=AsyncMock, return_value=mock_resp) as mock_req:
            await client._resolve_token_kind()
            await client._resolve_token_kind()
        # Should only call _raw_request once (cached after first success)
        assert mock_req.call_count == 1


# ===========================================================================
# DiscordClient — _get_json error handling
# ===========================================================================


class TestGetJsonErrors:
    async def test_401_raises_fatal(self):
        client = DiscordClient(token="t")
        resp = _make_mock_response(401)
        resp.is_success = False
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=resp):
            with pytest.raises(DiscordChatExporterError, match="Authentication token is invalid") as exc_info:
                await client._get_json("test/url")
            assert exc_info.value.is_fatal is True

    async def test_403_raises_forbidden(self):
        client = DiscordClient(token="t")
        resp = _make_mock_response(403)
        resp.is_success = False
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=resp):
            with pytest.raises(DiscordChatExporterError, match="forbidden"):
                await client._get_json("test/url")

    async def test_404_raises_not_found(self):
        client = DiscordClient(token="t")
        resp = _make_mock_response(404)
        resp.is_success = False
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=resp):
            with pytest.raises(DiscordChatExporterError, match="not found"):
                await client._get_json("test/url")

    async def test_500_raises_fatal(self):
        client = DiscordClient(token="t")
        resp = _make_mock_response(500)
        resp.is_success = False
        resp.text = "Internal Server Error"
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=resp):
            with pytest.raises(DiscordChatExporterError) as exc_info:
                await client._get_json("test/url")
            assert exc_info.value.is_fatal is True

    async def test_success_returns_json(self):
        client = DiscordClient(token="t")
        resp = _make_mock_response(200)
        resp.is_success = True
        resp.json.return_value = {"id": "123", "name": "test"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=resp):
            result = await client._get_json("test/url")
        assert result == {"id": "123", "name": "test"}


# ===========================================================================
# DiscordClient — _try_get_json
# ===========================================================================


class TestTryGetJson:
    async def test_success_returns_json(self):
        client = DiscordClient(token="t")
        resp = _make_mock_response(200)
        resp.is_success = True
        resp.json.return_value = {"data": "value"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=resp):
            result = await client._try_get_json("test/url")
        assert result == {"data": "value"}

    async def test_failure_returns_none(self):
        client = DiscordClient(token="t")
        resp = _make_mock_response(404)
        resp.is_success = False
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=resp):
            result = await client._try_get_json("test/url")
        assert result is None


# ===========================================================================
# DiscordClient — get_guild
# ===========================================================================


class TestGetGuild:
    async def test_dm_guild_returns_direct_messages(self):
        client = DiscordClient(token="t")
        result = await client.get_guild(Guild.DIRECT_MESSAGES.id)
        assert result is Guild.DIRECT_MESSAGES

    async def test_normal_guild(self):
        client = DiscordClient(token="t")
        guild_data = {"id": "12345", "name": "My Guild", "icon": None}
        with patch.object(client, "_get_json", new_callable=AsyncMock, return_value=guild_data):
            result = await client.get_guild(Snowflake(12345))
        assert result.id == Snowflake(12345)
        assert result.name == "My Guild"


# ===========================================================================
# DiscordClient — get_channels (DM guild path)
# ===========================================================================


class TestGetChannels:
    async def test_dm_guild_calls_get_dm_channels(self):
        client = DiscordClient(token="t")
        mock_channels = [MagicMock()]
        with patch.object(
            client, "get_dm_channels", new_callable=AsyncMock, return_value=mock_channels
        ):
            result = await client.get_channels(Guild.DIRECT_MESSAGES.id)
        assert result == mock_channels


# ===========================================================================
# DiscordClient — get_member
# ===========================================================================


class TestGetMember:
    async def test_dm_guild_returns_none(self):
        client = DiscordClient(token="t")
        result = await client.get_member(Guild.DIRECT_MESSAGES.id, Snowflake(123))
        assert result is None


# ===========================================================================
# DiscordClient — get_roles
# ===========================================================================


class TestGetRoles:
    async def test_dm_guild_returns_empty(self):
        client = DiscordClient(token="t")
        result = await client.get_roles(Guild.DIRECT_MESSAGES.id)
        assert result == []


# ===========================================================================
# DiscordClient — get_guilds
# ===========================================================================


class TestGetGuilds:
    async def test_returns_dm_guild_first(self):
        client = DiscordClient(token="t")
        # Return empty data to stop pagination after first page
        with patch.object(client, "_get_json", new_callable=AsyncMock, return_value=[]):
            guilds = await client.get_guilds()
        assert guilds[0] is Guild.DIRECT_MESSAGES

    async def test_paginates_guilds(self):
        client = DiscordClient(token="t")
        guild_data = [{"id": "100", "name": "Guild A", "icon": None}]

        call_count = 0

        async def mock_get_json(url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return guild_data
            return []  # End pagination

        with patch.object(client, "_get_json", side_effect=mock_get_json):
            guilds = await client.get_guilds()

        # DM guild + Guild A
        assert len(guilds) == 2
        assert guilds[0] is Guild.DIRECT_MESSAGES
        assert guilds[1].name == "Guild A"


# ===========================================================================
# DiscordClient — get_guild_threads
# ===========================================================================


class TestGetGuildThreads:
    async def test_dm_guild_returns_empty(self):
        client = DiscordClient(token="t")
        result = await client.get_guild_threads(Guild.DIRECT_MESSAGES.id)
        assert result == []


# ===========================================================================
# DiscordClient — get_members
# ===========================================================================


class TestGetMembers:
    async def test_dm_guild_returns_empty(self):
        client = DiscordClient(token="t")
        members = []
        async for member in client.get_members(Guild.DIRECT_MESSAGES.id):
            members.append(member)
        assert members == []


# ===========================================================================
# DiscordClient — rate limit handling
# ===========================================================================


class TestRateLimitHandling:
    async def test_rate_limit_sleeps(self):
        client = DiscordClient(token="t")
        client._resolved_token_kind = TokenKind.BOT

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.headers = httpx.Headers({
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset-After": "2.0",
        })
        mock_resp.is_success = True
        mock_http_client.get = AsyncMock(return_value=mock_resp)
        mock_http_client.is_closed = False
        client._client = mock_http_client

        with patch("discord_chat_exporter.core.discord.client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            # _raw_request is wrapped by @response_retry, but the inner function
            # still runs. Call it and check that sleep was invoked.
            resp = await client._raw_request("test", TokenKind.BOT)
            mock_sleep.assert_called_once()
            # delay = min(max(2.0 + 1.0, 0.0), 60.0) = 3.0
            mock_sleep.assert_called_with(3.0)

    async def test_no_sleep_when_remaining_positive(self):
        client = DiscordClient(token="t")
        client._resolved_token_kind = TokenKind.BOT

        mock_http_client = AsyncMock(spec=httpx.AsyncClient)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.headers = httpx.Headers({
            "X-RateLimit-Remaining": "5",
            "X-RateLimit-Reset-After": "2.0",
        })
        mock_resp.is_success = True
        mock_http_client.get = AsyncMock(return_value=mock_resp)
        mock_http_client.is_closed = False
        client._client = mock_http_client

        with patch("discord_chat_exporter.core.discord.client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            resp = await client._raw_request("test", TokenKind.BOT)
            mock_sleep.assert_not_called()


# ===========================================================================
# DiscordClient — lifecycle
# ===========================================================================


class TestClientLifecycle:
    async def test_context_manager(self):
        mock_async_client = MagicMock(spec=httpx.AsyncClient)
        mock_async_client.is_closed = False
        mock_async_client.aclose = AsyncMock()
        with patch(
            "discord_chat_exporter.core.discord.client.create_async_client",
            return_value=mock_async_client,
        ):
            async with DiscordClient(token="t") as client:
                assert client._client is not None
        assert client._client is None

    async def test_close(self):
        client = DiscordClient(token="t")
        mock_async_client = MagicMock(spec=httpx.AsyncClient)
        mock_async_client.is_closed = False
        mock_async_client.aclose = AsyncMock()
        with patch(
            "discord_chat_exporter.core.discord.client.create_async_client",
            return_value=mock_async_client,
        ):
            await client._get_client()
        assert client._client is not None
        await client.close()
        assert client._client is None

    async def test_close_when_already_closed(self):
        client = DiscordClient(token="t")
        # close without opening — should not raise
        await client.close()

    def test_init(self):
        client = DiscordClient(token="my-token")
        assert client._token == "my-token"
        assert client._resolved_token_kind is None
        assert client._client is None


# ===========================================================================
# ExportAssetDownloader — lifecycle
# ===========================================================================


class TestAssetDownloaderLifecycle:
    def test_init(self):
        d = ExportAssetDownloader(base_dir="/tmp/assets")
        assert d._base_dir == "/tmp/assets"
        assert d._should_reuse is True
        assert d._external_client is None

    def test_init_custom_params(self):
        client = MagicMock(spec=httpx.AsyncClient)
        d = ExportAssetDownloader(
            base_dir="/out",
            should_reuse=False,
            client=client,
            max_concurrency=4,
        )
        assert d._should_reuse is False
        assert d._external_client is client

    async def test_close(self):
        d = ExportAssetDownloader(base_dir="/tmp")
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.is_closed = False
        d._owned_client = mock_client
        await d.close()
        mock_client.aclose.assert_called_once()

    async def test_close_external_client_not_closed(self):
        mock_client = MagicMock(spec=httpx.AsyncClient)
        d = ExportAssetDownloader(base_dir="/tmp", client=mock_client)
        # close should not close the external client
        await d.close()
        mock_client.aclose.assert_not_called()
