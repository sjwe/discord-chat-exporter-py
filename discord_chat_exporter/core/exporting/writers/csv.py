"""CSV message writer."""

from __future__ import annotations

import io
from typing import IO, TYPE_CHECKING

from discord_chat_exporter.core.exporting.writers.base import MessageWriter

if TYPE_CHECKING:
    from discord_chat_exporter.core.discord.models.message import Message
    from discord_chat_exporter.core.exporting.context import ExportContext


def _csv_encode(value: str) -> str:
    # Prevent CSV formula injection: prefix dangerous characters with a tab
    if value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        value = "\t" + value
    return '"' + value.replace('"', '""') + '"'


class CsvMessageWriter(MessageWriter):
    def __init__(self, stream: IO[bytes], context: ExportContext) -> None:
        super().__init__(stream, context)
        self._writer = io.TextIOWrapper(stream, encoding="utf-8", newline="\n")

    async def _format_markdown(self, text: str) -> str:
        if self.context.request.should_format_markdown:
            from discord_chat_exporter.core.markdown.plaintext_visitor import (
                PlainTextMarkdownVisitor,
            )

            return await PlainTextMarkdownVisitor.format(self.context, text)
        return text

    async def write_preamble(self) -> None:
        self._writer.write("AuthorID,Author,Date,Content,Attachments,Reactions\n")
        self._writer.flush()

    async def write_message(self, message: Message) -> None:
        await super().write_message(message)
        w = self._writer

        # Author ID
        w.write(_csv_encode(str(message.author.id)))
        w.write(",")

        # Author name
        w.write(_csv_encode(message.author.full_name))
        w.write(",")

        # Timestamp (ISO format)
        w.write(_csv_encode(self.context.normalize_date(message.timestamp).isoformat()))
        w.write(",")

        # Content
        if message.is_system_notification:
            w.write(_csv_encode(self.context.get_fallback_content(message)))
        else:
            w.write(_csv_encode(await self._format_markdown(message.content)))
        w.write(",")

        # Attachments
        att_urls = []
        for att in message.attachments:
            att_urls.append(await self.context.resolve_asset_url(att.url))
        w.write(_csv_encode(",".join(att_urls)))
        w.write(",")

        # Reactions
        reaction_parts = []
        for reaction in message.reactions:
            reaction_parts.append(f"{reaction.emoji.name} ({reaction.count})")
        w.write(_csv_encode(",".join(reaction_parts)))

        w.write("\n")
        w.flush()

    async def close(self) -> None:
        self._writer.flush()
        self._writer.detach()
        await super().close()
