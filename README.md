# Discord Chat Exporter (Python)

A CLI tool to export Discord chat logs to a file. Python port of [DiscordChatExporter](https://github.com/Tyrrrz/DiscordChatExporter).

## Features

- Export channels, threads, and DMs
- Multiple output formats: HTML (dark/light), JSON, CSV, plain text
- Message filtering DSL (`from:user`, `has:image`, `reaction:emoji`, boolean operators)
- Export partitioning by message count or file size
- Optional media/asset downloading
- Discord markdown rendering (bold, italic, code, mentions, emoji, timestamps, etc.)
- Parallel channel exports
- Rate-limit handling with automatic retry
- MCP server mode for LLM integration (STDIO + HTTP transports)

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Installation

```bash
# Clone and install with uv
git clone <repo-url>
cd discord_chat_exporter-py
uv sync

# Or install with pip
pip install -e .
```

## Usage

All commands require a Discord token, passed via `-t` or the `DISCORD_TOKEN` environment variable.

```bash
export DISCORD_TOKEN="your-token-here"
```

### List guilds

```bash
discord-chat-exporter guilds
```

### List channels in a guild

```bash
discord-chat-exporter channels <guild-id>
```

### List DM channels

```bash
discord-chat-exporter dm
```

### Export channels

```bash
# Export a single channel (default: HTML dark theme)
discord-chat-exporter export <channel-id>

# Export multiple channels
discord-chat-exporter export <channel-id-1> <channel-id-2>

# Specify format and output path
discord-chat-exporter export <channel-id> -f json -o ./exports/

# Export with media download
discord-chat-exporter export <channel-id> --media

# Export with date range
discord-chat-exporter export <channel-id> --after 2024-01-01 --before 2024-12-31

# Export with message filter
discord-chat-exporter export <channel-id> --filter "from:username has:image"

# Export with partitioning
discord-chat-exporter export <channel-id> --partition 10mb

# Parallel export (4 channels at once)
discord-chat-exporter export <id1> <id2> <id3> <id4> --parallel 4
```

### Export all channels in a guild

```bash
discord-chat-exporter exportall <guild-id>

# Include threads
discord-chat-exporter exportall <guild-id> --threads all
```

### Export all DMs

```bash
discord-chat-exporter exportdm
```

## Export Formats

| Format | Flag | Description |
|--------|------|-------------|
| HTML (Dark) | `-f htmldark` | Styled HTML mimicking Discord's dark theme (default) |
| HTML (Light) | `-f htmllight` | Styled HTML mimicking Discord's light theme |
| JSON | `-f json` | Structured JSON with full message metadata |
| CSV | `-f csv` | Tabular format with author, date, content, attachments, reactions |
| Plain Text | `-f plaintext` | Simple text format |

## Output Path Templating

The `-o` flag supports placeholders:

| Placeholder | Value |
|-------------|-------|
| `%g` | Guild ID |
| `%G` | Guild name |
| `%c` | Channel ID |
| `%C` | Channel name |
| `%t` | Parent category ID |
| `%T` | Parent category name |
| `%p` | Channel position |
| `%a` | After date |
| `%b` | Before date |
| `%d` | Current date |
| `%%` | Literal `%` |

Example: `-o "./exports/%G/%C.html"`

## Message Filter DSL

Filter expressions support:

| Filter | Example | Description |
|--------|---------|-------------|
| `from:` | `from:username` | Messages by a specific user |
| `mentions:` | `mentions:username` | Messages mentioning a user |
| `has:` | `has:image` | Messages with attachments (`link`, `embed`, `file`, `video`, `image`, `sound`, `pin`, `invite`) |
| `reaction:` | `reaction:thumbsup` | Messages with a specific reaction |
| bare text | `hello world` | Messages containing text |

Operators:

- `&` or whitespace — AND
- `|` — OR
- `-` or `~` — NOT
- `()` — grouping

Example: `from:alice has:image | (from:bob -has:link)`

## MCP Server Mode

The MCP (Model Context Protocol) server allows LLMs to programmatically query Discord data. It exposes 4 tools and supports both STDIO and HTTP transports.

### Running the MCP server

```bash
# STDIO transport (default, for MCP client integration)
DISCORD_TOKEN="your-token" python -m discord_chat_exporter.mcp

# HTTP transport
DISCORD_TOKEN="your-token" python -m discord_chat_exporter.mcp --transport http --port 8000

# Via installed script
DISCORD_TOKEN="your-token" discord-chat-exporter-mcp
```

### Adding to Claude Code

```bash
claude mcp add --transport stdio -e DISCORD_TOKEN=your-token \
  -- discord-chat-exporter uv run python -m discord_chat_exporter.mcp
```

### MCP Tools

| Tool | Parameters | Returns |
|------|-----------|---------|
| `list_guilds` | none | List of `{id, name}` for all accessible guilds |
| `list_channels` | `guild_id` | List of `{id, name, kind, topic, parent_id, parent_name}` |
| `list_dm_channels` | none | List of `{id, name}` for DM channels |
| `get_messages` | `channel_id`, `format`, `after`, `before`, `filter`, `max_words` | Formatted message text |

### get_messages parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `channel_id` | required | Discord channel ID |
| `format` | `"plaintext"` | Output format: `plaintext`, `json`, or `csv` |
| `after` | `null` | Only messages after this ISO date or snowflake ID |
| `before` | `null` | Only messages before this ISO date or snowflake ID |
| `filter` | `null` | Filter DSL expression (e.g. `"from:user has:image"`) |
| `max_words` | `4000` | Approximate word cap on response size |

When `max_words` is exceeded, output is properly closed (valid JSON/CSV) with a truncation note. Use the `after` parameter with the last message timestamp to paginate.

## Running with Python module

```bash
python -m discord_chat_exporter guilds
python -m discord_chat_exporter export <channel-id>
```

## Development

```bash
# Install dev dependencies
uv sync

# Run tests
uv run pytest

# Lint
uv run ruff check .

# Type check
uv run mypy .
```

## Project Structure

```
discord_chat_exporter/
  cli/app.py                  # Click CLI commands
  mcp/
    server.py                 # MCP server with 4 tools (FastMCP)
    __main__.py               # Entry point: python -m discord_chat_exporter.mcp
  core/
    discord/
      client.py               # Async Discord API client
      snowflake.py             # Discord snowflake ID type
      models/                  # Pydantic models (guild, channel, message, etc.)
    exporting/
      channel_exporter.py      # Single-channel export orchestration
      message_exporter.py      # Message writing with partition support
      context.py               # Export context (caches, asset resolution)
      request.py               # Export request config with path templating
      format.py                # Export format enum
      partitioning.py          # File size / message count partitioning
      asset_downloader.py      # Media file downloader
      filtering/               # Message filter DSL (parser + filters)
      writers/                 # Format-specific writers (html, json, csv, txt)
    markdown/
      parser.py                # Regex-based Discord markdown parser
      nodes.py                 # Markdown AST node types
      html_visitor.py          # Markdown AST to HTML
      plaintext_visitor.py     # Markdown AST to plain text
    utils/http.py              # httpx client config and retry logic
  templates/html/              # Jinja2 HTML export templates
```

## License

This project is a Python port of [DiscordChatExporter](https://github.com/Tyrrrz/DiscordChatExporter) by Tyrrrz.
