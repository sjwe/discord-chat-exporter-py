"""HTML message writer with Jinja2 templates."""

from __future__ import annotations

import io
from datetime import datetime
from html import escape as html_escape
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

import jinja2

from discord_chat_exporter.core.discord.models.embed import EmbedKind
from discord_chat_exporter.core.discord.models.message import MessageFlags, MessageKind
from discord_chat_exporter.core.discord.models.sticker import StickerFormat
from discord_chat_exporter.core.exporting.writers.base import MessageWriter

if TYPE_CHECKING:
    from discord_chat_exporter.core.discord.models.embed import Embed, EmbedAuthor
    from discord_chat_exporter.core.discord.models.message import Message
    from discord_chat_exporter.core.exporting.context import ExportContext

_TEMPLATE_DIR = str(
    Path(__file__).resolve().parent.parent.parent.parent / "templates" / "html"
)


def _make_themed(theme_name: str):
    """Create a themed() function for dark/light value selection."""

    def themed(dark: str, light: str) -> str:
        return dark if theme_name == "Dark" else light

    return themed


def _color_css(hex_color: str | None) -> str | None:
    """Convert '#rrggbb' to 'rgb(r, g, b)' or return None."""
    if not hex_color:
        return None
    h = hex_color.lstrip("#")
    return f"rgb({int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)})"


def _color_rgba(hex_color: str) -> str:
    """Convert '#rrggbb' to 'rgba(r, g, b, 1)'."""
    h = hex_color.lstrip("#")
    return f"rgba({int(h[0:2], 16)}, {int(h[2:4], 16)}, {int(h[4:6], 16)}, 1)"


class HtmlMessageWriter(MessageWriter):
    """Writes messages to an HTML file using Jinja2 templates."""

    def __init__(self, stream: IO[bytes], context: ExportContext, theme_name: str) -> None:
        super().__init__(stream, context)
        self._writer = io.TextIOWrapper(stream, encoding="utf-8", newline="\n")
        self._theme_name = theme_name
        self._message_group: list[Message] = []
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(_TEMPLATE_DIR),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    # -- grouping --

    def _can_join_group(self, message: Message) -> bool:
        if not self._message_group:
            return True
        last = self._message_group[-1]
        if message.is_reply_like:
            return False
        if message.is_system_notification:
            if not last.is_system_notification:
                return False
        else:
            if last.is_system_notification:
                return False
            if abs((message.timestamp - last.timestamp).total_seconds()) / 60 > 7:
                return False
            if message.author.id != last.author.id:
                return False
            if message.author.full_name != last.author.full_name:
                return False
        return True

    # -- markdown helpers --

    async def _format_markdown(self, text: str) -> str:
        if self.context.request.should_format_markdown:
            from discord_chat_exporter.core.markdown.html_visitor import HtmlMarkdownVisitor

            return await HtmlMarkdownVisitor.format(self.context, text, is_jumbo_allowed=True)
        return html_escape(text)

    async def _format_embed_markdown(self, text: str) -> str:
        if self.context.request.should_format_markdown:
            from discord_chat_exporter.core.markdown.html_visitor import HtmlMarkdownVisitor

            return await HtmlMarkdownVisitor.format(self.context, text, is_jumbo_allowed=False)
        return html_escape(text)

    # -- date/time --

    def _fmt_date(self, dt: datetime, fmt: str = "g") -> str:
        return self.context.format_date(dt, fmt)

    # -- system notification HTML --

    def _build_sys_html(self, message: Message) -> str:
        kind = message.kind
        e = html_escape

        if kind == MessageKind.RECIPIENT_ADD and message.mentioned_users:
            u = message.mentioned_users[0]
            return (
                f'added <a class="chatlog__system-notification-link" '
                f'title="{e(u.full_name)}">{e(u.display_name)}</a> to the group.'
            )
        if kind == MessageKind.RECIPIENT_REMOVE and message.mentioned_users:
            u = message.mentioned_users[0]
            if message.author.id == u.id:
                return "left the group."
            return (
                f'removed <a class="chatlog__system-notification-link" '
                f'title="{e(u.full_name)}">{e(u.display_name)}</a> from the group.'
            )
        if kind == MessageKind.CALL:
            end = message.call_ended_timestamp or message.timestamp
            minutes = abs((end - message.timestamp).total_seconds()) / 60
            return f"started a call that lasted {minutes:,.0f} minutes"
        if kind == MessageKind.CHANNEL_NAME_CHANGE:
            return (
                f'changed the channel name: '
                f'<span class="chatlog__system-notification-link">{e(message.content)}</span>'
            )
        if kind == MessageKind.CHANNEL_ICON_CHANGE:
            return "changed the channel icon."
        if kind == MessageKind.CHANNEL_PINNED_MESSAGE and message.reference:
            mid = message.reference.message_id
            return (
                f'pinned <a class="chatlog__system-notification-link" '
                f'href="#chatlog__message-container-{mid}">a message</a> to this channel.'
            )
        if kind == MessageKind.THREAD_CREATED:
            return "started a thread."
        if kind == MessageKind.GUILD_MEMBER_JOIN:
            return "joined the server."
        return e(message.content.lower())

    # -- pre-process messages --

    async def _prepare_message(self, message: Message, is_first: bool) -> dict[str, Any]:
        ctx = self.context

        author_member = ctx.try_get_member(message.author.id)
        author_color = ctx.try_get_user_color(message.author.id)
        author_display_name = (
            message.author.display_name
            if message.author.is_bot
            else (author_member.display_name if author_member else None)
            or message.author.display_name
        )
        author_avatar_url = await ctx.resolve_asset_url(
            (author_member.avatar_url if author_member and author_member.avatar_url else None)
            or message.author.avatar_url
        )

        # Content
        content_html = ""
        if message.content.strip():
            content_html = await self._format_markdown(message.content)

        # System notification
        sys_icon_map = {
            MessageKind.RECIPIENT_ADD: "join-icon",
            MessageKind.RECIPIENT_REMOVE: "leave-icon",
            MessageKind.CALL: "call-icon",
            MessageKind.CHANNEL_NAME_CHANGE: "pencil-icon",
            MessageKind.CHANNEL_ICON_CHANGE: "pencil-icon",
            MessageKind.CHANNEL_PINNED_MESSAGE: "pin-icon",
            MessageKind.GUILD_MEMBER_JOIN: "join-icon",
            MessageKind.THREAD_CREATED: "thread-icon",
        }
        sys_icon = sys_icon_map.get(message.kind, "pencil-icon")
        sys_html = self._build_sys_html(message) if message.is_system_notification else ""

        # Reply / interaction reference
        reply = await self._prepare_reply(message) if is_first and message.is_reply_like else None

        # Attachments
        attachments = []
        for att in message.attachments:
            att_url = await ctx.resolve_asset_url(att.url)
            attachments.append({
                "url": att_url,
                "file_name": att.file_name,
                "file_size": att.file_size_display,
                "description": att.description,
                "is_image": att.is_image,
                "is_video": att.is_video,
                "is_audio": att.is_audio,
                "is_spoiler": att.is_spoiler,
            })

        # Embeds
        embeds = [await self._prepare_embed(emb) for emb in message.embeds]

        # Stickers
        stickers = []
        for sticker in message.stickers:
            sticker_url = await ctx.resolve_asset_url(sticker.source_url)
            stickers.append({
                "name": sticker.name,
                "url": sticker_url,
                "is_image": sticker.is_image,
                "is_lottie": sticker.format == StickerFormat.LOTTIE,
            })

        # Reactions
        reactions = []
        for reaction in message.reactions:
            emoji_url = await ctx.resolve_asset_url(reaction.emoji.image_url)
            reactions.append({
                "name": reaction.emoji.name,
                "code": reaction.emoji.code,
                "url": emoji_url,
                "count": reaction.count,
            })

        return {
            "id": str(message.id),
            "is_first": is_first,
            "is_system": message.is_system_notification,
            "is_pinned": message.is_pinned,
            "is_reply_like": message.is_reply_like,
            "is_bot": message.author.is_bot,
            "is_crosspost": bool(message.flags & MessageFlags.CROSS_POST),
            "author_display_name": author_display_name,
            "author_full_name": message.author.full_name,
            "author_id": str(message.author.id),
            "author_color": _color_css(author_color),
            "author_avatar_url": author_avatar_url,
            "sys_icon": sys_icon,
            "sys_html": sys_html,
            "content_html": content_html,
            "has_content": bool(message.content.strip()),
            "reply": reply,
            "attachments": attachments,
            "embeds": embeds,
            "stickers": stickers,
            "reactions": reactions,
            "ts_full": self._fmt_date(message.timestamp, "f"),
            "ts_short": self._fmt_date(message.timestamp, "t"),
            "ts_display": self._fmt_date(message.timestamp),
            "edited_ts": (
                self._fmt_date(message.edited_timestamp, "f")
                if message.edited_timestamp
                else None
            ),
        }

    async def _prepare_reply(self, message: Message) -> dict[str, Any]:
        ctx = self.context

        if message.referenced_message is not None:
            ref = message.referenced_message
            ref_member = ctx.try_get_member(ref.author.id)
            ref_color = ctx.try_get_user_color(ref.author.id)
            ref_name = (
                ref.author.display_name
                if ref.author.is_bot
                else (ref_member.display_name if ref_member else None)
                or ref.author.display_name
            )
            ref_avatar = await ctx.resolve_asset_url(
                (ref_member.avatar_url if ref_member and ref_member.avatar_url else None)
                or ref.author.avatar_url
            )
            ref_html = ""
            if ref.content.strip():
                ref_html = await self._format_embed_markdown(ref.content)
            return {
                "kind": "message",
                "id": str(ref.id),
                "avatar_url": ref_avatar,
                "name": ref_name,
                "full_name": ref.author.full_name,
                "color": _color_css(ref_color),
                "html": ref_html,
                "has_content": bool(ref.content.strip()),
                "has_attachments": bool(ref.attachments) or bool(ref.embeds),
                "edited_ts": (
                    self._fmt_date(ref.edited_timestamp, "f")
                    if ref.edited_timestamp
                    else None
                ),
            }

        if message.interaction is not None:
            inter = message.interaction
            inter_member = ctx.try_get_member(inter.user.id)
            inter_color = ctx.try_get_user_color(inter.user.id)
            inter_name = (
                inter.user.display_name
                if inter.user.is_bot
                else (inter_member.display_name if inter_member else None)
                or inter.user.display_name
            )
            inter_avatar = await ctx.resolve_asset_url(
                (inter_member.avatar_url if inter_member and inter_member.avatar_url else None)
                or inter.user.avatar_url
            )
            return {
                "kind": "interaction",
                "avatar_url": inter_avatar,
                "name": inter_name,
                "full_name": inter.user.full_name,
                "color": _color_css(inter_color),
                "command": inter.name,
            }

        return {"kind": "deleted"}

    async def _prepare_embed(self, embed: Embed) -> dict[str, Any]:
        ctx = self.context

        spotify = embed.try_get_spotify_track()
        if spotify:
            return {"type": "spotify", "url": spotify.url}

        youtube = embed.try_get_youtube_video()
        if youtube:
            d: dict[str, Any] = {"type": "youtube", "video_url": youtube.url}
            d["color_css"] = _color_rgba(embed.color) if embed.color else None
            if embed.author:
                d["author"] = await self._prepare_embed_author(embed.author)
            if embed.title and embed.title.strip():
                d["title_html"] = await self._format_embed_markdown(embed.title)
                d["title_url"] = embed.url
            return d

        if embed.kind == EmbedKind.IMAGE and embed.url:
            img_url = (
                (embed.image.proxy_url if embed.image and embed.image.proxy_url else None)
                or (embed.image.url if embed.image else None)
                or (embed.thumbnail.proxy_url if embed.thumbnail and embed.thumbnail.proxy_url else None)
                or (embed.thumbnail.url if embed.thumbnail else None)
                or embed.url
            )
            return {
                "type": "image",
                "url": await ctx.resolve_asset_url(img_url),
                "canonical_url": (embed.image.url if embed.image else None)
                or (embed.thumbnail.url if embed.thumbnail else None)
                or embed.url,
            }

        twitch = embed.try_get_twitch_clip()
        if embed.kind == EmbedKind.VIDEO and embed.url and twitch is None:
            vid_url = (
                (embed.video.proxy_url if embed.video and embed.video.proxy_url else None)
                or (embed.video.url if embed.video else None)
                or embed.url
            )
            return {
                "type": "video",
                "url": await ctx.resolve_asset_url(vid_url),
                "canonical_url": (embed.video.url if embed.video else None) or embed.url,
                "width": embed.video.width if embed.video else None,
                "height": embed.video.height if embed.video else None,
            }

        if embed.kind == EmbedKind.GIFV and embed.url:
            vid_url = (
                (embed.video.proxy_url if embed.video and embed.video.proxy_url else None)
                or (embed.video.url if embed.video else None)
                or embed.url
            )
            return {
                "type": "gifv",
                "url": await ctx.resolve_asset_url(vid_url),
                "canonical_url": (embed.video.url if embed.video else None) or embed.url,
                "width": embed.video.width if embed.video else None,
                "height": embed.video.height if embed.video else None,
            }

        # Rich embed
        d = {"type": "rich"}
        d["color_css"] = _color_rgba(embed.color) if embed.color else None

        if embed.author:
            d["author"] = await self._prepare_embed_author(embed.author)

        if embed.title and embed.title.strip():
            d["title_html"] = await self._format_embed_markdown(embed.title)
            d["title_url"] = embed.url

        if embed.description and embed.description.strip():
            d["description_html"] = await self._format_embed_markdown(embed.description)

        if embed.fields:
            fields = []
            for f in embed.fields:
                fd: dict[str, Any] = {"is_inline": f.is_inline}
                if f.name and f.name.strip():
                    fd["name_html"] = await self._format_embed_markdown(f.name)
                if f.value and f.value.strip():
                    fd["value_html"] = await self._format_embed_markdown(f.value)
                fields.append(fd)
            d["fields"] = fields

        if embed.thumbnail and embed.thumbnail.url:
            thumb = embed.thumbnail.proxy_url or embed.thumbnail.url
            d["thumbnail"] = {
                "url": await ctx.resolve_asset_url(thumb),
                "canonical_url": embed.thumbnail.url,
            }

        if embed.images:
            imgs = []
            for img in embed.images:
                if img.url:
                    src = img.proxy_url or img.url
                    imgs.append({
                        "url": await ctx.resolve_asset_url(src),
                        "canonical_url": img.url,
                    })
            if imgs:
                d["images"] = imgs

        if embed.footer or embed.timestamp:
            footer: dict[str, Any] = {}
            if embed.footer:
                if embed.footer.icon_url:
                    footer["icon_url"] = await ctx.resolve_asset_url(
                        embed.footer.icon_proxy_url or embed.footer.icon_url
                    )
                    footer["icon_canonical_url"] = embed.footer.icon_url
                if embed.footer.text:
                    footer["text"] = embed.footer.text
            if embed.timestamp:
                footer["timestamp"] = self._fmt_date(embed.timestamp)
            d["footer"] = footer

        return d

    async def _prepare_embed_author(self, author: EmbedAuthor) -> dict[str, Any]:
        r: dict[str, Any] = {}
        if author.icon_url:
            r["icon_url"] = await self.context.resolve_asset_url(
                author.icon_proxy_url or author.icon_url
            )
            r["icon_canonical_url"] = author.icon_url
        if author.name:
            r["name"] = author.name
            r["url"] = author.url
        return r

    # -- write lifecycle --

    async def write_preamble(self) -> None:
        ctx = self.context
        req = ctx.request
        themed = _make_themed(self._theme_name)

        # Pre-resolve font URLs
        font_urls = {}
        for style in ("normal", "italic"):
            for weight in (400, 500, 600, 700, 800):
                url = f"https://cdn.jsdelivr.net/gh/Tyrrrz/DiscordFonts@master/ggsans-{style}-{weight}.woff2"
                font_urls[(style, weight)] = await ctx.resolve_asset_url(url)

        theme_lower = self._theme_name.lower()
        hljs_css_url = await ctx.resolve_asset_url(
            f"https://cdnjs.cloudflare.com/ajax/libs/highlight.js/9.15.6/styles/solarized-{theme_lower}.min.css"
        )
        hljs_js_url = await ctx.resolve_asset_url(
            "https://cdnjs.cloudflare.com/ajax/libs/highlight.js/9.15.6/highlight.min.js"
        )
        lottie_url = await ctx.resolve_asset_url(
            "https://cdnjs.cloudflare.com/ajax/libs/lottie-web/5.8.1/lottie.min.js"
        )

        guild_icon_url = await ctx.resolve_asset_url(
            req.channel.icon_url or req.guild.icon_url
        )

        channel_topic_html = None
        if req.channel.topic and req.channel.topic.strip():
            channel_topic_html = await self._format_markdown(req.channel.topic)

        date_range_text = None
        if req.after is not None or req.before is not None:
            if req.after is not None and req.before is not None:
                date_range_text = (
                    f"Between {self._fmt_date(req.after.to_date())} "
                    f"and {self._fmt_date(req.before.to_date())}"
                )
            elif req.after is not None:
                date_range_text = f"After {self._fmt_date(req.after.to_date())}"
            elif req.before is not None:
                date_range_text = f"Before {self._fmt_date(req.before.to_date())}"

        template = self._env.get_template("preamble.html.j2")
        html = template.render(
            themed=themed,
            theme_name=self._theme_name,
            guild_name=req.guild.name,
            channel_name=req.channel.name,
            channel_hierarchical_name=req.channel.get_hierarchical_name(),
            channel_topic_html=channel_topic_html,
            guild_icon_url=guild_icon_url,
            date_range_text=date_range_text,
            font_urls=font_urls,
            hljs_css_url=hljs_css_url,
            hljs_js_url=hljs_js_url,
            lottie_url=lottie_url,
        )
        self._writer.write(html + "\n")
        self._writer.flush()

    async def _write_message_group(self, messages: list[Message]) -> None:
        prepared = []
        for i, msg in enumerate(messages):
            prepared.append(await self._prepare_message(msg, is_first=(i == 0)))

        template = self._env.get_template("message_group.html.j2")
        html = template.render(messages=prepared)
        self._writer.write(html + "\n")
        self._writer.flush()

    async def write_message(self, message: Message) -> None:
        await super().write_message(message)
        if self._can_join_group(message):
            self._message_group.append(message)
        else:
            await self._write_message_group(self._message_group)
            self._message_group.clear()
            self._message_group.append(message)

    async def write_postamble(self) -> None:
        if self._message_group:
            await self._write_message_group(self._message_group)
            self._message_group.clear()

        import time

        if self.context.request.is_utc_normalization_enabled:
            tz_offset = 0.0
        else:
            tz_offset = -time.timezone / 3600
            if time.daylight:
                tz_offset = -time.altzone / 3600

        if tz_offset == 0:
            tz_text = "+0"
        elif tz_offset > 0:
            tz_text = f"+{tz_offset:g}"
        else:
            tz_text = f"{tz_offset:g}"

        template = self._env.get_template("postamble.html.j2")
        html = template.render(
            messages_written=f"{self.messages_written:,}",
            timezone_text=tz_text,
        )
        self._writer.write(html + "\n")
        self._writer.flush()

    async def close(self) -> None:
        self._writer.flush()
        self._writer.detach()
        await super().close()
