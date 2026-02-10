"""JSON message writer - streaming JSON output."""

from __future__ import annotations

import io
import json
from datetime import datetime
from typing import IO, TYPE_CHECKING

from discord_chat_exporter.core.exporting.writers.base import MessageWriter

if TYPE_CHECKING:
    from discord_chat_exporter.core.discord.models.embed import (
        Embed,
        EmbedAuthor,
        EmbedField,
        EmbedFooter,
        EmbedImage,
        EmbedVideo,
    )
    from discord_chat_exporter.core.discord.models.emoji import Emoji
    from discord_chat_exporter.core.discord.models.message import Message
    from discord_chat_exporter.core.discord.models.role import Role
    from discord_chat_exporter.core.discord.models.user import User
    from discord_chat_exporter.core.exporting.context import ExportContext


class JsonMessageWriter(MessageWriter):
    def __init__(self, stream: IO[bytes], context: ExportContext) -> None:
        super().__init__(stream, context)
        self._writer = io.TextIOWrapper(stream, encoding="utf-8", newline="\n")
        self._first_message = True

    def _write_json(self, obj: object) -> None:
        self._writer.write(json.dumps(obj, ensure_ascii=False, default=str))

    async def _format_markdown(self, text: str) -> str:
        if self.context.request.should_format_markdown:
            from discord_chat_exporter.core.markdown.plaintext_visitor import (
                PlainTextMarkdownVisitor,
            )

            return await PlainTextMarkdownVisitor.format(self.context, text)
        return text

    def _format_date(self, dt: datetime | None) -> str | None:
        if dt is None:
            return None
        return self.context.normalize_date(dt).isoformat()

    async def _build_user(self, user: User, include_roles: bool = True) -> dict:
        member = self.context.try_get_member(user.id)
        avatar_url = await self.context.resolve_asset_url(
            (member.avatar_url if member and member.avatar_url else None) or user.avatar_url
        )

        result: dict = {
            "id": str(user.id),
            "name": user.name,
            "discriminator": user.discriminator_formatted,
            "nickname": (member.display_name if member else None) or user.display_name,
            "color": self.context.try_get_user_color(user.id),
            "isBot": user.is_bot,
            "avatarUrl": avatar_url,
        }

        if include_roles:
            result["roles"] = [
                self._build_role(r) for r in self.context.get_user_roles(user.id)
            ]

        return result

    @staticmethod
    def _build_role(role: Role) -> dict:
        return {
            "id": str(role.id),
            "name": role.name,
            "color": role.color,
            "position": role.position,
        }

    async def _build_emoji(self, emoji: Emoji) -> dict:
        return {
            "id": str(emoji.id) if emoji.id else None,
            "name": emoji.name,
            "code": emoji.code,
            "isAnimated": emoji.is_animated,
            "imageUrl": await self.context.resolve_asset_url(emoji.image_url),
        }

    async def _build_embed_author(self, author: EmbedAuthor) -> dict:
        result: dict = {"name": author.name, "url": author.url}
        if author.icon_url:
            result["iconUrl"] = await self.context.resolve_asset_url(
                author.icon_proxy_url or author.icon_url
            )
            result["iconCanonicalUrl"] = author.icon_url
        return result

    async def _build_embed_image(self, image: EmbedImage) -> dict:
        result: dict = {}
        if image.url:
            result["url"] = await self.context.resolve_asset_url(
                image.proxy_url or image.url
            )
            result["canonicalUrl"] = image.url
        result["width"] = image.width
        result["height"] = image.height
        return result

    async def _build_embed_video(self, video: EmbedVideo) -> dict:
        result: dict = {}
        if video.url:
            result["url"] = await self.context.resolve_asset_url(
                video.proxy_url or video.url
            )
            result["canonicalUrl"] = video.url
        result["width"] = video.width
        result["height"] = video.height
        return result

    async def _build_embed_footer(self, footer: EmbedFooter) -> dict:
        result: dict = {"text": footer.text}
        if footer.icon_url:
            result["iconUrl"] = await self.context.resolve_asset_url(
                footer.icon_proxy_url or footer.icon_url
            )
            result["iconCanonicalUrl"] = footer.icon_url
        return result

    async def _build_embed_field(self, field: EmbedField) -> dict:
        return {
            "name": await self._format_markdown(field.name),
            "value": await self._format_markdown(field.value),
            "isInline": field.is_inline,
        }

    async def _build_embed(self, embed: Embed) -> dict:
        result: dict = {
            "title": await self._format_markdown(embed.title or ""),
            "url": embed.url,
            "timestamp": self._format_date(embed.timestamp),
            "description": await self._format_markdown(embed.description or ""),
        }

        if embed.color:
            result["color"] = embed.color

        if embed.author:
            result["author"] = await self._build_embed_author(embed.author)
        if embed.thumbnail:
            result["thumbnail"] = await self._build_embed_image(embed.thumbnail)
        if embed.image:
            result["image"] = await self._build_embed_image(embed.image)
        if embed.video:
            result["video"] = await self._build_embed_video(embed.video)
        if embed.footer:
            result["footer"] = await self._build_embed_footer(embed.footer)

        result["images"] = [await self._build_embed_image(img) for img in embed.images]
        result["fields"] = [await self._build_embed_field(f) for f in embed.fields]

        # Inline emoji from description
        inline_emojis: list[dict] = []
        if embed.description:
            from discord_chat_exporter.core.markdown.parser import extract_emojis

            seen: set[str] = set()
            for emoji_node in extract_emojis(embed.description):
                from discord_chat_exporter.core.discord.models.emoji import Emoji

                if emoji_node.name not in seen:
                    seen.add(emoji_node.name)
                    emoji = Emoji(
                        id=emoji_node.id, name=emoji_node.name, is_animated=emoji_node.is_animated
                    )
                    inline_emojis.append(await self._build_emoji(emoji))

        result["inlineEmojis"] = inline_emojis
        return result

    async def write_preamble(self) -> None:
        w = self._writer
        req = self.context.request

        guild_icon = await self.context.resolve_asset_url(req.guild.icon_url)

        preamble = {
            "guild": {
                "id": str(req.guild.id),
                "name": req.guild.name,
                "iconUrl": guild_icon,
            },
            "channel": {
                "id": str(req.channel.id),
                "type": req.channel.kind.name,
                "categoryId": str(req.channel.parent.id) if req.channel.parent else None,
                "category": req.channel.parent.name if req.channel.parent else None,
                "name": req.channel.name,
                "topic": req.channel.topic,
            },
            "dateRange": {
                "after": self._format_date(req.after.to_date()) if req.after else None,
                "before": self._format_date(req.before.to_date()) if req.before else None,
            },
            "exportedAt": self._format_date(datetime.now()),
        }

        if req.channel.icon_url:
            preamble["channel"]["iconUrl"] = await self.context.resolve_asset_url(
                req.channel.icon_url
            )

        # Write opening JSON manually for streaming
        w.write("{\n")
        for key in ("guild", "channel", "dateRange", "exportedAt"):
            w.write(f"  {json.dumps(key)}: ")
            w.write(json.dumps(preamble[key], ensure_ascii=False, default=str))
            w.write(",\n")

        w.write('  "messages": [\n')
        w.flush()

    async def write_message(self, message: Message) -> None:
        await super().write_message(message)
        w = self._writer

        if not self._first_message:
            w.write(",\n")
        self._first_message = False

        # Build message object
        if message.is_system_notification:
            content = self.context.get_fallback_content(message)
        else:
            content = await self._format_markdown(message.content)

        msg_obj: dict = {
            "id": str(message.id),
            "type": message.kind.name,
            "timestamp": self._format_date(message.timestamp),
            "timestampEdited": self._format_date(message.edited_timestamp),
            "callEndedTimestamp": self._format_date(message.call_ended_timestamp),
            "isPinned": message.is_pinned,
            "content": content,
            "author": await self._build_user(message.author, include_roles=True),
        }

        # Attachments
        attachments = []
        for att in message.attachments:
            attachments.append({
                "id": str(att.id),
                "url": await self.context.resolve_asset_url(att.url),
                "fileName": att.file_name,
                "fileSizeBytes": att.file_size_bytes,
            })
        msg_obj["attachments"] = attachments

        # Embeds
        msg_obj["embeds"] = [await self._build_embed(e) for e in message.embeds]

        # Stickers
        stickers = []
        for sticker in message.stickers:
            stickers.append({
                "id": str(sticker.id),
                "name": sticker.name,
                "format": sticker.format.name,
                "sourceUrl": await self.context.resolve_asset_url(sticker.source_url),
            })
        msg_obj["stickers"] = stickers

        # Reactions
        reactions = []
        for reaction in message.reactions:
            reactions.append({
                "emoji": await self._build_emoji(reaction.emoji),
                "count": reaction.count,
            })
        msg_obj["reactions"] = reactions

        # Mentions
        msg_obj["mentions"] = [
            await self._build_user(u, include_roles=True) for u in message.mentioned_users
        ]

        # Reference
        if message.reference:
            msg_obj["reference"] = {
                "messageId": str(message.reference.message_id) if message.reference.message_id else None,
                "channelId": str(message.reference.channel_id) if message.reference.channel_id else None,
                "guildId": str(message.reference.guild_id) if message.reference.guild_id else None,
            }

        # Interaction
        if message.interaction:
            msg_obj["interaction"] = {
                "id": str(message.interaction.id),
                "name": message.interaction.name,
                "user": await self._build_user(message.interaction.user, include_roles=True),
            }

        # Inline emojis
        from discord_chat_exporter.core.markdown.parser import extract_emojis
        from discord_chat_exporter.core.discord.models.emoji import Emoji

        inline_emojis: list[dict] = []
        seen: set[str] = set()
        for emoji_node in extract_emojis(message.content):
            if emoji_node.name not in seen:
                seen.add(emoji_node.name)
                emoji = Emoji(
                    id=emoji_node.id, name=emoji_node.name, is_animated=emoji_node.is_animated
                )
                inline_emojis.append(await self._build_emoji(emoji))
        msg_obj["inlineEmojis"] = inline_emojis

        # Write indented JSON
        msg_json = json.dumps(msg_obj, ensure_ascii=False, indent=2, default=str)
        # Indent each line by 4 spaces
        indented = "\n".join("    " + line for line in msg_json.split("\n"))
        w.write(indented)
        w.flush()

    async def write_postamble(self) -> None:
        w = self._writer
        w.write("\n  ],\n")
        w.write(f'  "messageCount": {self.messages_written}\n')
        w.write("}\n")
        w.flush()

    async def close(self) -> None:
        self._writer.flush()
        self._writer.detach()
        await super().close()
