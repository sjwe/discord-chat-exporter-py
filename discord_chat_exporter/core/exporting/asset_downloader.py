"""Asset downloader for media files referenced in exports."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx

# Domains that are safe to download assets from.
_ALLOWED_DOMAINS = frozenset({
    "cdn.discordapp.com",
    "media.discordapp.net",
    "images-ext-1.discordapp.net",
    "images-ext-2.discordapp.net",
    # CDN services commonly used for embeds
    "cdnjs.cloudflare.com",
    "cdn.jsdelivr.net",
})

# Maximum response size: 50 MB
_MAX_RESPONSE_SIZE = 50 * 1024 * 1024

# Maximum concurrent downloads
_DEFAULT_CONCURRENCY = 8


def _is_url_allowed(url: str) -> bool:
    """Check if a URL's domain is in the allowlist."""
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        return host in _ALLOWED_DOMAINS
    except Exception:
        return False


class ExportAssetDownloader:
    """Downloads and caches assets locally during export."""

    def __init__(
        self,
        base_dir: str,
        should_reuse: bool = True,
        client: httpx.AsyncClient | None = None,
        max_concurrency: int = _DEFAULT_CONCURRENCY,
    ) -> None:
        self._base_dir = base_dir
        self._should_reuse = should_reuse
        self._external_client = client
        self._owned_client: httpx.AsyncClient | None = None
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def _get_client(self) -> httpx.AsyncClient:
        """Return the shared HTTP client, creating one if needed."""
        if self._external_client is not None:
            return self._external_client
        if self._owned_client is None or self._owned_client.is_closed:
            self._owned_client = httpx.AsyncClient(
                follow_redirects=True, timeout=30.0
            )
        return self._owned_client

    async def close(self) -> None:
        """Close the owned HTTP client if one was created."""
        if self._owned_client is not None and not self._owned_client.is_closed:
            await self._owned_client.aclose()
            self._owned_client = None

    async def _get_lock(self, key: str) -> asyncio.Lock:
        async with self._global_lock:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Strip CDN-specific query params that don't affect content."""
        parsed = urlparse(url)
        # Remove Discord CDN size/format params
        clean = parsed._replace(query="", fragment="")
        return clean.geturl()

    @staticmethod
    def _get_file_name_from_url(url: str) -> str:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        name = Path(path).name if path else "unknown"
        # Sanitize
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
        return name or "unknown"

    def _get_file_path(self, url: str) -> str:
        url_hash = hashlib.sha256(self._normalize_url(url).encode()).hexdigest()[:16]
        file_name = self._get_file_name_from_url(url)
        stem = Path(file_name).stem
        suffix = Path(file_name).suffix
        # Include hash to avoid collisions
        safe_name = f"{stem}-{url_hash}{suffix}"
        return os.path.join(self._base_dir, safe_name)

    async def download(self, url: str) -> str:
        """Download an asset and return the local file path.

        Only downloads from allowed domains. Returns the original URL
        if the domain is not in the allowlist.
        """
        if not _is_url_allowed(url):
            return url

        file_path = self._get_file_path(url)

        # Reuse existing file if allowed
        if self._should_reuse and os.path.exists(file_path):
            return file_path

        lock = await self._get_lock(file_path)
        async with self._semaphore:
            async with lock:
                # Double-check after acquiring lock
                if self._should_reuse and os.path.exists(file_path):
                    return file_path

                os.makedirs(os.path.dirname(file_path), exist_ok=True)

                client = await self._get_client()
                # Use streaming to enforce size limits without loading everything into memory
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    total = 0
                    with open(file_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            total += len(chunk)
                            if total > _MAX_RESPONSE_SIZE:
                                raise ValueError(
                                    f"Response exceeds maximum size of "
                                    f"{_MAX_RESPONSE_SIZE // (1024 * 1024)} MB"
                                )
                            f.write(chunk)

                return file_path
