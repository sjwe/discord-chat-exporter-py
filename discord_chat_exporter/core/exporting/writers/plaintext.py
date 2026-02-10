"""Plain text message writer."""

from __future__ import annotations

import io
from typing import IO, TYPE_CHECKING

from discord_chat_exporter.core.exporting.writers.base import MessageWriter

if TYPE_CHECKING:
    from discord_chat_exporter.core.discord.models.message import Message
    from discord_chat_exporter.core.exporting.context import ExportContext


class PlainTextMessageWriter(MessageWriter):
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
        w = self._writer
        w.write("=" * 62 + "\n")
        w.write(f"Guild: {self.context.request.guild.name}\n")
        w.write(f"Channel: {self.context.request.channel.get_hierarchical_name()}\n")

        if self.context.request.channel.topic:
            w.write(f"Topic: {self.context.request.channel.topic}\n")

        if self.context.request.after is not None:
            w.write(
                f"After: {self.context.format_date(self.context.request.after.to_date())}\n"
            )
        if self.context.request.before is not None:
            w.write(
                f"Before: {self.context.format_date(self.context.request.before.to_date())}\n"
            )

        w.write("=" * 62 + "\n\n")
        w.flush()

    async def write_message(self, message: Message) -> None:
        await super().write_message(message)
        w = self._writer

        # Header
        w.write(f"[{self.context.format_date(message.timestamp)}]")
        w.write(f" {message.author.full_name}")
        if message.is_pinned:
            w.write(" (pinned)")
        w.write("\n")

        # Content
        if message.is_system_notification:
            w.write(self.context.get_fallback_content(message) + "\n")
        else:
            w.write(await self._format_markdown(message.content) + "\n")

        w.write("\n")

        # Attachments
        if message.attachments:
            w.write("{Attachments}\n")
            for att in message.attachments:
                w.write(await self.context.resolve_asset_url(att.url) + "\n")
            w.write("\n")

        # Embeds
        for embed in message.embeds:
            w.write("{Embed}\n")
            if embed.author and embed.author.name:
                w.write(embed.author.name + "\n")
            if embed.url:
                w.write(embed.url + "\n")
            if embed.title:
                w.write(await self._format_markdown(embed.title) + "\n")
            if embed.description:
                w.write(await self._format_markdown(embed.description) + "\n")
            for field in embed.fields:
                if field.name:
                    w.write(await self._format_markdown(field.name) + "\n")
                if field.value:
                    w.write(await self._format_markdown(field.value) + "\n")
            if embed.thumbnail and embed.thumbnail.url:
                url = embed.thumbnail.proxy_url or embed.thumbnail.url
                w.write(await self.context.resolve_asset_url(url) + "\n")
            for img in embed.images:
                if img.url:
                    url = img.proxy_url or img.url
                    w.write(await self.context.resolve_asset_url(url) + "\n")
            if embed.footer and embed.footer.text:
                w.write(embed.footer.text + "\n")
            w.write("\n")

        # Stickers
        if message.stickers:
            w.write("{Stickers}\n")
            for sticker in message.stickers:
                w.write(await self.context.resolve_asset_url(sticker.source_url) + "\n")
            w.write("\n")

        # Reactions
        if message.reactions:
            w.write("{Reactions}\n")
            parts = []
            for reaction in message.reactions:
                part = reaction.emoji.name
                if reaction.count > 1:
                    part += f" ({reaction.count})"
                parts.append(part)
            w.write(" ".join(parts) + "\n")

        w.write("\n")
        w.flush()

    async def write_postamble(self) -> None:
        w = self._writer
        w.write("=" * 62 + "\n")
        w.write(f"Exported {self.messages_written:,} message(s)\n")
        w.write("=" * 62 + "\n")
        w.flush()

    async def close(self) -> None:
        self._writer.flush()
        self._writer.detach()  # Don't close underlying stream twice
        await super().close()
