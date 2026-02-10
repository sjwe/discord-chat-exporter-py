"""Asset downloader for media files referenced in exports."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx


class ExportAssetDownloader:
    """Downloads and caches assets locally during export."""

    def __init__(self, base_dir: str, should_reuse: bool = True) -> None:
        self._base_dir = base_dir
        self._should_reuse = should_reuse
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

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
        """Download an asset and return the local file path."""
        file_path = self._get_file_path(url)

        # Reuse existing file if allowed
        if self._should_reuse and os.path.exists(file_path):
            return file_path

        lock = await self._get_lock(file_path)
        async with lock:
            # Double-check after acquiring lock
            if self._should_reuse and os.path.exists(file_path):
                return file_path

            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
                response = await client.get(url)
                response.raise_for_status()

                with open(file_path, "wb") as f:
                    f.write(response.content)

            return file_path
