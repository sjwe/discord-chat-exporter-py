"""Base message writer ABC."""

from __future__ import annotations

from typing import IO, TYPE_CHECKING

if TYPE_CHECKING:
    from discord_chat_exporter.core.discord.models.message import Message
    from discord_chat_exporter.core.exporting.context import ExportContext


class MessageWriter:
    """Abstract base for all export format writers."""

    def __init__(self, stream: IO[bytes], context: ExportContext) -> None:
        self._stream = stream
        self.context = context
        self.messages_written: int = 0

    @property
    def bytes_written(self) -> int:
        return self._stream.tell()

    async def write_preamble(self) -> None:
        pass

    async def write_message(self, message: Message) -> None:
        self.messages_written += 1

    async def write_postamble(self) -> None:
        pass

    async def close(self) -> None:
        self._stream.close()
