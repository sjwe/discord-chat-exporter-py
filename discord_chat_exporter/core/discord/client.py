"""Discord API client with rate-limiting, retry, and pagination support."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator
from enum import Enum
from typing import Any
from urllib.parse import quote as url_quote

import httpx

from discord_chat_exporter.core.discord.models import (
    Channel,
    ChannelKind,
    Emoji,
    Guild,
    Member,
    Message,
    Role,
    User,
)
from discord_chat_exporter.core.discord.snowflake import Snowflake
from discord_chat_exporter.core.exceptions import DiscordChatExporterError
from discord_chat_exporter.core.utils.http import create_async_client, response_retry

logger = logging.getLogger(__name__)

_BASE_URL = "https://discord.com/api/v10/"
_PAGE_SIZE = 100


class TokenKind(Enum):
    USER = "user"
    BOT = "bot"


class Invite:
    """Lightweight invite representation returned by ``get_invite``."""

    __slots__ = ("code", "guild", "channel")

    def __init__(
        self,
        code: str,
        guild: Guild | None = None,
        channel: Channel | None = None,
    ) -> None:
        self.code = code
        self.guild = guild
        self.channel = channel

    _CODE_RE = re.compile(r"^https?://discord\.gg/(\w+)/?$")

    @classmethod
    def try_get_code_from_url(cls, url: str) -> str | None:
        m = cls._CODE_RE.match(url)
        return m.group(1) if m else None


class DiscordClient:
    """Async Discord API client.

    Parameters
    ----------
    token:
        Discord authentication token (bot or user).
    """

    def __init__(self, token: str) -> None:
        self._token = token
        self._resolved_token_kind: TokenKind | None = None
        self._client: httpx.AsyncClient | None = None

    # -- lifecycle ----------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = create_async_client()
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> DiscordClient:
        await self._get_client()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # -- low-level request helpers ------------------------------------------

    def _auth_header(self, token_kind: TokenKind) -> str:
        if token_kind == TokenKind.BOT:
            return f"Bot {self._token}"
        return self._token

    @response_retry
    async def _raw_request(
        self,
        url: str,
        token_kind: TokenKind,
    ) -> httpx.Response:
        """Execute a single GET request with retry (via ``response_retry``).

        Rate-limit headers are respected *inside* this method: if
        ``X-RateLimit-Remaining`` drops to 0, we sleep for the reset delay
        (capped at 60 s) before returning the response.
        """
        client = await self._get_client()
        full_url = _BASE_URL + url

        response = await client.get(
            full_url,
            headers={
                # Don't let httpx validate the value -- tokens may contain
                # special characters.
                "Authorization": self._auth_header(token_kind),
            },
        )

        # Advisory rate-limit handling: if we just used the last remaining
        # request in the bucket, sleep before returning so that the *next*
        # call won't be rejected.
        remaining_raw = response.headers.get("X-RateLimit-Remaining")
        reset_after_raw = response.headers.get("X-RateLimit-Reset-After")

        if remaining_raw is not None and reset_after_raw is not None:
            try:
                remaining = int(remaining_raw)
                reset_after = float(reset_after_raw)
            except (ValueError, TypeError):
                remaining = 1
                reset_after = 0.0

            if remaining <= 0:
                # Add a 1-second buffer; cap at 60 s (Discord sometimes sends
                # absurdly high values).
                delay = min(max(reset_after + 1.0, 0.0), 60.0)
                logger.debug("Rate-limited: sleeping %.1f s", delay)
                await asyncio.sleep(delay)

        return response

    async def _resolve_token_kind(self) -> TokenKind:
        """Auto-detect whether the token is a user or bot token.

        Tries user-style auth first, falls back to bot-style auth.  Caches the
        result for subsequent requests.
        """
        if self._resolved_token_kind is not None:
            return self._resolved_token_kind

        # Try authenticating as a user
        user_resp = await self._raw_request("users/@me", TokenKind.USER)
        if user_resp.status_code != 401:
            self._resolved_token_kind = TokenKind.USER
            return TokenKind.USER

        # Try authenticating as a bot
        bot_resp = await self._raw_request("users/@me", TokenKind.BOT)
        if bot_resp.status_code != 401:
            self._resolved_token_kind = TokenKind.BOT
            return TokenKind.BOT

        raise DiscordChatExporterError("Authentication token is invalid.", is_fatal=True)

    async def _request(self, url: str) -> httpx.Response:
        """Make an authenticated GET request with auto-detected token type."""
        token_kind = await self._resolve_token_kind()
        return await self._raw_request(url, token_kind)

    async def _get_json(self, url: str) -> Any:
        """GET *url* and return the parsed JSON body.

        Raises ``DiscordChatExporterError`` on 401, 403, 404 and other error
        status codes.
        """
        response = await self._request(url)

        if response.is_success:
            return response.json()

        status = response.status_code
        if status == 401:
            raise DiscordChatExporterError(
                "Authentication token is invalid.",
                is_fatal=True,
            )
        if status == 403:
            raise DiscordChatExporterError(
                f"Request to '{url}' failed: forbidden.",
            )
        if status == 404:
            raise DiscordChatExporterError(
                f"Request to '{url}' failed: not found.",
            )

        # Generic server error
        body = response.text
        raise DiscordChatExporterError(
            f"Request to '{url}' failed: {status}. Response content: {body}",
            is_fatal=True,
        )

    async def _try_get_json(self, url: str) -> Any | None:
        """GET *url* and return parsed JSON, or ``None`` on non-success."""
        response = await self._request(url)
        if response.is_success:
            return response.json()
        return None

    # -- public API ---------------------------------------------------------

    # ---- guilds -----------------------------------------------------------

    async def get_guilds(self) -> AsyncIterator[Guild]:
        """List all guilds accessible to the authenticated user.

        Yields the synthetic *Direct Messages* guild first, then paginates
        through the real guilds.
        """
        yield Guild.DIRECT_MESSAGES

        current_after = Snowflake.ZERO
        while True:
            url = (
                f"users/@me/guilds?limit={_PAGE_SIZE}"
                f"&after={current_after}"
            )
            data = await self._get_json(url)

            if not data:
                return

            for guild_json in data:
                guild = Guild.model_validate(guild_json)
                yield guild
                current_after = guild.id

    async def get_guild(self, guild_id: Snowflake) -> Guild:
        """Fetch a single guild by ID."""
        if guild_id == Guild.DIRECT_MESSAGES.id:
            return Guild.DIRECT_MESSAGES

        data = await self._get_json(f"guilds/{guild_id}")
        return Guild.model_validate(data)

    # ---- channels ---------------------------------------------------------

    async def get_channels(self, guild_id: Snowflake) -> list[Channel]:
        """List channels in a guild, sorted by position.

        For the DM pseudo-guild, returns the user's DM channels instead.
        """
        if guild_id == Guild.DIRECT_MESSAGES.id:
            return await self.get_dm_channels()

        data = await self._get_json(f"guilds/{guild_id}/channels")

        # Sort by (position, id) to match the C# client's behaviour.
        sorted_data = sorted(
            data,
            key=lambda j: (j.get("position", 0), int(j.get("id", "0"))),
        )

        # Build a lookup of category channels so we can inject them as parents.
        parents_by_id: dict[Snowflake, Channel] = {}
        for i, ch_json in enumerate(sorted_data):
            if ch_json.get("type") == int(ChannelKind.GUILD_CATEGORY):
                chan = Channel.model_validate({**ch_json, "parent": None})
                parents_by_id[chan.id] = chan

        channels: list[Channel] = []
        for position, ch_json in enumerate(sorted_data):
            parent_id_raw = ch_json.get("parent_id")
            parent: Channel | None = None
            if parent_id_raw:
                parent = parents_by_id.get(Snowflake.parse(str(parent_id_raw)))

            channel = Channel.model_validate({
                **ch_json,
                "parent": parent,
                "position": position,
            })
            channels.append(channel)

        return channels

    async def get_guild_threads(
        self,
        guild_id: Snowflake,
    ) -> list[Channel]:
        """List active threads in a guild.

        For bot accounts this uses ``guilds/{id}/threads/active``.  The full
        archived-thread logic from the C# client is complex (user vs bot paths)
        and can be extended later; this covers the primary use case.
        """
        if guild_id == Guild.DIRECT_MESSAGES.id:
            return []

        # Build parent-channel lookup so threads can reference their parent.
        parent_channels = await self.get_channels(guild_id)
        parents_by_id: dict[Snowflake, Channel] = {ch.id: ch for ch in parent_channels}

        data = await self._try_get_json(f"guilds/{guild_id}/threads/active")
        if data is None:
            return []

        threads: list[Channel] = []
        for thread_json in data.get("threads", []):
            parent_id_raw = thread_json.get("parent_id")
            parent: Channel | None = None
            if parent_id_raw:
                parent = parents_by_id.get(Snowflake.parse(str(parent_id_raw)))

            thread = Channel.model_validate({**thread_json, "parent": parent})
            threads.append(thread)

        return threads

    async def get_channel(self, channel_id: Snowflake) -> Channel:
        """Fetch a single channel, resolving its parent category if present."""
        data = await self._get_json(f"channels/{channel_id}")

        parent_id_raw = data.get("parent_id")
        parent: Channel | None = None
        if parent_id_raw:
            try:
                parent = await self.get_channel(Snowflake.parse(str(parent_id_raw)))
            except DiscordChatExporterError:
                # The parent channel may be inaccessible even though the child
                # channel is accessible.
                pass

        return Channel.model_validate({**data, "parent": parent})

    async def get_channel_category(self, channel_id: Snowflake) -> Channel | None:
        """Return the parent category of a channel, or None."""
        channel = await self.get_channel(channel_id)
        if channel.parent is not None:
            return channel.parent
        return None

    # ---- messages ---------------------------------------------------------

    async def get_messages(
        self,
        channel_id: Snowflake,
        after: Snowflake | None = None,
        before: Snowflake | None = None,
    ) -> AsyncIterator[Message]:
        """Paginate through messages in a channel.

        Yields ``Message`` objects from oldest to newest within the given
        boundaries.  Uses pages of 100, iterating until an empty page is
        returned.
        """
        # Snapshot the last message so we know when to stop.
        last_message = await self._try_get_last_message(channel_id, before)
        if last_message is None:
            return
        if after is not None and last_message.timestamp < after.to_date():
            return

        current_after = after or Snowflake.ZERO
        while True:
            url = (
                f"channels/{channel_id}/messages"
                f"?limit={_PAGE_SIZE}"
                f"&after={current_after}"
            )
            data = await self._get_json(url)

            # Messages come newest-first from the API; reverse to yield
            # oldest-first, matching the C# client.
            messages = [Message.model_validate(m) for m in reversed(data)]

            if not messages:
                return

            for message in messages:
                # Stop if we've gone past the snapshot boundary.
                if message.timestamp > last_message.timestamp:
                    return

                yield message
                current_after = message.id

    async def _try_get_last_message(
        self,
        channel_id: Snowflake,
        before: Snowflake | None = None,
    ) -> Message | None:
        """Fetch the single most-recent message (optionally before a bound)."""
        url = f"channels/{channel_id}/messages?limit=1"
        if before is not None:
            url += f"&before={before}"

        data = await self._get_json(url)
        if not data:
            return None

        return Message.model_validate(data[-1])

    # ---- members ----------------------------------------------------------

    async def get_members(self, guild_id: Snowflake) -> AsyncIterator[Member]:
        """Paginate through all members of a guild.

        Yields ``Member`` objects, paginated with ``after`` in batches of 100.
        """
        if guild_id == Guild.DIRECT_MESSAGES.id:
            return

        current_after = Snowflake.ZERO
        while True:
            url = (
                f"guilds/{guild_id}/members"
                f"?limit={_PAGE_SIZE}"
                f"&after={current_after}"
            )
            data = await self._try_get_json(url)

            if not data:
                return

            for member_json in data:
                # Inject guild_id so the model validator can build avatar URLs.
                member_json["_guild_id"] = guild_id
                member = Member.model_validate(member_json)
                yield member
                current_after = member.id

    async def get_member(
        self,
        guild_id: Snowflake,
        user_id: Snowflake,
    ) -> Member | None:
        """Fetch a single guild member, or ``None`` if inaccessible."""
        if guild_id == Guild.DIRECT_MESSAGES.id:
            return None

        data = await self._try_get_json(f"guilds/{guild_id}/members/{user_id}")
        if data is None:
            return None

        data["_guild_id"] = guild_id
        return Member.model_validate(data)

    # ---- roles ------------------------------------------------------------

    async def get_roles(self, guild_id: Snowflake) -> list[Role]:
        """List all roles in a guild."""
        if guild_id == Guild.DIRECT_MESSAGES.id:
            return []

        data = await self._get_json(f"guilds/{guild_id}/roles")
        return [Role.model_validate(r) for r in data]

    # ---- DM channels ------------------------------------------------------

    async def get_dm_channels(self) -> list[Channel]:
        """List the authenticated user's DM channels."""
        data = await self._get_json("users/@me/channels")
        return [Channel.model_validate(ch) for ch in data]

    # ---- invites ----------------------------------------------------------

    async def get_invite(self, code: str) -> Invite | None:
        """Fetch invite metadata, or ``None`` if the invite is invalid."""
        data = await self._try_get_json(f"invites/{code}")
        if data is None:
            return None

        guild_json = data.get("guild")
        guild = Guild.model_validate(guild_json) if guild_json else Guild.DIRECT_MESSAGES

        channel_json = data.get("channel")
        channel = Channel.model_validate(channel_json) if channel_json else None

        return Invite(
            code=data["code"],
            guild=guild,
            channel=channel,
        )

    # ---- reactions --------------------------------------------------------

    async def get_message_reactions(
        self,
        channel_id: Snowflake,
        message_id: Snowflake,
        emoji: Emoji,
    ) -> AsyncIterator[User]:
        """Paginate through users who reacted with *emoji* on a message."""
        # Build the emoji identifier: "name:id" for custom, just "name" for standard.
        if emoji.id is not None:
            reaction_name = f"{emoji.name}:{emoji.id}"
        else:
            reaction_name = emoji.name

        encoded_name = url_quote(reaction_name, safe="")

        current_after = Snowflake.ZERO
        while True:
            url = (
                f"channels/{channel_id}/messages/{message_id}"
                f"/reactions/{encoded_name}"
                f"?limit={_PAGE_SIZE}&after={current_after}"
            )
            data = await self._try_get_json(url)
            if not data:
                return

            for user_json in data:
                user = User.model_validate(user_json)
                yield user
                current_after = user.id
