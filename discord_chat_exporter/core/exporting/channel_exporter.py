"""Channel exporter - orchestrates the export of a single channel."""

from __future__ import annotations

from typing import TYPE_CHECKING

from discord_chat_exporter.core.discord.models.channel import ChannelKind
from discord_chat_exporter.core.exceptions import ChannelEmptyError, DiscordChatExporterError

if TYPE_CHECKING:
    from discord_chat_exporter.core.discord.client import DiscordClient
    from discord_chat_exporter.core.exporting.request import ExportRequest


class ChannelExporter:
    """Exports messages from a single Discord channel."""

    def __init__(self, client: DiscordClient) -> None:
        self._client = client

    async def export(self, request: ExportRequest) -> None:
        from discord_chat_exporter.core.exporting.context import ExportContext
        from discord_chat_exporter.core.exporting.message_exporter import MessageExporter

        # Forum channels can't be exported directly
        if request.channel.kind == ChannelKind.GUILD_FORUM:
            raise DiscordChatExporterError(
                f"Channel '{request.channel.name}' "
                f"of guild '{request.guild.name}' "
                "is a forum and cannot be exported directly. "
                "You need to pull its threads and export them individually.",
                is_fatal=True,
            )

        # Build context and populate caches
        context = ExportContext(self._client, request)
        await context.populate_channels_and_roles()

        # Initialize the exporter
        exporter = MessageExporter(context)

        try:
            # Check if channel is empty
            if request.channel.is_empty:
                raise ChannelEmptyError(
                    f"Channel '{request.channel.name}' "
                    f"of guild '{request.guild.name}' "
                    "does not contain any messages; an empty file will be created."
                )

            # Check boundary validity
            if request.before and not request.channel.may_have_messages_before(request.before):
                raise ChannelEmptyError(
                    f"Channel '{request.channel.name}' "
                    f"of guild '{request.guild.name}' "
                    "does not contain any messages within the specified period."
                )
            if request.after and not request.channel.may_have_messages_after(request.after):
                raise ChannelEmptyError(
                    f"Channel '{request.channel.name}' "
                    f"of guild '{request.guild.name}' "
                    "does not contain any messages within the specified period."
                )

            # Iterate messages and export
            async for message in self._client.get_messages(
                request.channel.id,
                after=request.after,
                before=request.before,
            ):
                try:
                    # Populate member cache for referenced users
                    for user in message.get_referenced_users():
                        await context.populate_member(user)

                    # Apply filter and export
                    if request.message_filter.is_match(message):
                        await exporter.export_message(message)

                except DiscordChatExporterError:
                    raise
                except Exception as ex:
                    raise DiscordChatExporterError(
                        f"Failed to export message #{message.id} "
                        f"in channel '{request.channel.name}' (#{request.channel.id}) "
                        f"of guild '{request.guild.name} (#{request.guild.id})'.",
                        is_fatal=True,
                    ) from ex

        finally:
            await exporter.close()
            await context.close()
