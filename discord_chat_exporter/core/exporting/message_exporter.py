"""Message exporter with partitioning support."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from discord_chat_exporter.core.exporting.format import ExportFormat
from discord_chat_exporter.core.exporting.writers.base import MessageWriter

if TYPE_CHECKING:
    from discord_chat_exporter.core.discord.models.message import Message
    from discord_chat_exporter.core.exporting.context import ExportContext


def _get_partition_file_path(base_path: str, partition_index: int) -> str:
    if partition_index <= 0:
        return base_path
    p = Path(base_path)
    return str(p.parent / f"{p.stem} [part {partition_index + 1}]{p.suffix}")


def _create_writer(file_path: str, fmt: ExportFormat, context: ExportContext) -> MessageWriter:
    try:
        stream = open(file_path, "wb")  # noqa: SIM115
    except OSError:
        raise

    try:
        if fmt == ExportFormat.PLAIN_TEXT:
            from discord_chat_exporter.core.exporting.writers.plaintext import PlainTextMessageWriter

            return PlainTextMessageWriter(stream, context)
        elif fmt == ExportFormat.CSV:
            from discord_chat_exporter.core.exporting.writers.csv import CsvMessageWriter

            return CsvMessageWriter(stream, context)
        elif fmt in (ExportFormat.HTML_DARK, ExportFormat.HTML_LIGHT):
            from discord_chat_exporter.core.exporting.writers.html import HtmlMessageWriter

            theme = "Dark" if fmt == ExportFormat.HTML_DARK else "Light"
            return HtmlMessageWriter(stream, context, theme)
        elif fmt == ExportFormat.JSON:
            from discord_chat_exporter.core.exporting.writers.json import JsonMessageWriter

            return JsonMessageWriter(stream, context)
        else:
            raise ValueError(f"Unknown export format: {fmt}")
    except Exception:
        stream.close()
        raise


class MessageExporter:
    """Handles writing messages with partition support."""

    def __init__(self, context: ExportContext) -> None:
        self._context = context
        self._partition_index = 0
        self._writer: MessageWriter | None = None
        self.messages_exported: int = 0

    async def _initialize_writer(self) -> MessageWriter:
        # Check if partition limit reached
        if self._writer is not None:
            if self._context.request.partition_limit.is_reached(
                self._writer.messages_written,
                self._writer.bytes_written,
            ):
                await self._uninitialize_writer()
                self._partition_index += 1

        if self._writer is not None:
            return self._writer

        os.makedirs(self._context.request.output_dir_path, exist_ok=True)
        file_path = _get_partition_file_path(
            self._context.request.output_file_path,
            self._partition_index,
        )

        writer = _create_writer(file_path, self._context.request.export_format, self._context)
        await writer.write_preamble()
        self._writer = writer
        return writer

    async def _uninitialize_writer(self) -> None:
        if self._writer is not None:
            try:
                await self._writer.write_postamble()
            finally:
                await self._writer.close()
                self._writer = None

    async def export_message(self, message: Message) -> None:
        writer = await self._initialize_writer()
        await writer.write_message(message)
        self.messages_exported += 1

    async def close(self) -> None:
        # If no messages were written, force creation of an empty file
        if self.messages_exported <= 0:
            await self._initialize_writer()
        await self._uninitialize_writer()
