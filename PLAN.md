# Plan: Convert DiscordChatExporter (C#) to Pure Python

## Context

The C# project at `../DiscordChatExporter` is a mature, feature-rich Discord chat archival tool built on .NET with CLI + GUI layers. The goal is to convert the **CLI and Core** functionality to a pure Python package, maintaining full feature parity with the C# CLI.

The C# tool supports 5 export formats (PlainText, HtmlDark, HtmlLight, CSV, JSON), a message filtering DSL, Discord markdown processing, media downloading, file partitioning, thread inclusion, and parallel channel export. All of this needs to be faithfully ported.

**Confirmed scope:** CLI only (no GUI/TUI), Python 3.12+, uv for project management.

---

## Dependencies

| Package | Replaces (C#) | Why |
|---------|---------------|-----|
| `httpx` | HttpClient | Async HTTP with HTTP/2, clean API |
| `click` | CliFx | Mature CLI framework, better custom type support than typer |
| `rich` | Spectre.Console | Progress bars, colored output, spinners |
| `jinja2` | RazorBlade | HTML templating |
| `pydantic` | Manual JSON parsing | JSON->model with validation, aliases, validators |
| `tenacity` | Polly | Retry with exponential backoff |
| `htmlmin` | WebMarkupMin | HTML minification |
| `aiofiles` | System.IO async | Async file I/O for downloads |

Dev: `pytest`, `pytest-asyncio`, `pytest-httpx`, `ruff`, `mypy`
Build: `uv` (fast, modern Python package manager)

---

## Package Structure

```
discord_chat_exporter/
    __init__.py
    __main__.py                       # python -m discord_chat_exporter
    cli/
        __init__.py
        app.py                        # Main click group + all commands
        converters.py                 # Click param types (Snowflake, PartitionLimit, ExportFormat)
        progress.py                   # Rich progress display
    core/
        __init__.py
        discord/
            __init__.py
            client.py                 # DiscordClient (async, all endpoints)
            snowflake.py              # Snowflake value type
            models/
                __init__.py           # Re-exports
                guild.py
                channel.py            # Channel, ChannelKind
                message.py            # Message, MessageKind, MessageFlags
                user.py               # User
                member.py             # Member
                attachment.py         # Attachment
                embed.py              # Embed + sub-models
                emoji.py              # Emoji + EmojiIndex
                reaction.py
                role.py
                sticker.py
                cdn.py                # ImageCdn URL helpers
        exporting/
            __init__.py
            request.py                # ExportRequest (path templating)
            context.py                # ExportContext (caches, asset resolution)
            format.py                 # ExportFormat enum
            channel_exporter.py       # Orchestrator
            message_exporter.py       # Partitioning logic
            writers/
                __init__.py
                base.py               # MessageWriter ABC
                plaintext.py
                csv.py
                html.py               # HtmlMessageWriter + Jinja2
                json.py               # JsonMessageWriter (streaming)
            partitioning.py           # PartitionLimit
            asset_downloader.py       # Download + hash + keyed lock
            filtering/
                __init__.py
                base.py               # MessageFilter ABC
                filters.py            # Contains, From, Has, Mentions, Reaction
                combinators.py        # Binary, Negated, Null
                parser.py             # Hand-rolled recursive descent
        markdown/
            __init__.py
            nodes.py                  # AST nodes
            parser.py                 # Regex-based parser (port C# matchers exactly)
            visitor.py                # Base visitor
            html_visitor.py
            plaintext_visitor.py
        utils/
            __init__.py
            http.py                   # Shared httpx client config, retry pipeline
    templates/
        html/
            preamble.html.j2
            message_group.html.j2
            postamble.html.j2
tests/
    conftest.py
    test_snowflake.py
    test_markdown.py
    test_filters.py
    test_writers.py
    test_client.py
pyproject.toml
```

---

## Key Design Decisions

1. **Pydantic v2 for models** - Each C# model has a `Parse(JsonElement)` factory. Pydantic's `model_validate()` with `alias` and `@model_validator` replaces this with ~60% less code.

2. **Snowflake as frozen dataclass** (not Pydantic) - Needs to be hashable for use as dict keys. Wraps `int`, provides `to_date()`, `from_date()`, `parse()`, comparison operators.

3. **Async throughout** - `httpx.AsyncClient` + `async for` pagination (replaces C# `IAsyncEnumerable`). CLI uses `asyncio.run()` at the top level.

4. **Pre-resolve async data for HTML templates** - Instead of calling async functions inside Jinja2 templates, resolve all asset URLs and format all markdown *before* passing data to templates. Cleaner than hacking async into Jinja2.

5. **Hand-rolled filter parser** (~120 lines) - The grammar is small enough that `lark` is overkill. Recursive descent handles: `contains:`, `from:`, `has:`, `mentions:`, `reaction:`, `&`, `|`, `-`/`~`, parentheses, implicit AND.

6. **Streaming JSON writer** - Write array delimiters manually, use `json.dumps()` per message object. Avoids loading all messages into memory.

7. **Rate limiting** - Read `X-RateLimit-Remaining` / `X-RateLimit-Reset-After` headers. Configurable respect levels. Max 60s wait cap. `tenacity` for retry (exponential backoff, 8 attempts, retryable: 429/408/5xx).

---

## Implementation Phases

### Phase 1: Foundation
- `pyproject.toml` with uv, all deps, entry point `discord-chat-exporter`
- `Snowflake` type with timestamp extraction, parsing, comparison
- All Pydantic domain models (Guild, Channel, User, Member, Message, Attachment, Embed, Emoji, Reaction, Role, Sticker)
- `ImageCdn` URL helpers
- `ExportFormat` enum
- Click CLI skeleton with stub commands

**Key source files to port:**
- `Core/Discord/Data/*.cs` -> `core/discord/models/`
- `Core/Discord/Snowflake.cs` -> `core/discord/snowflake.py`
- `Core/Discord/Data/Common/ImageCdn.cs` -> `core/discord/models/cdn.py`

### Phase 2: Discord API Client
- `DiscordClient` with all endpoints, pagination, auth auto-detection
- Rate limiting + retry via tenacity
- Error types (`DiscordChatExporterException`, `ChannelEmptyException`)
- Wire up `guilds`, `channels`, `dm` commands

**Key source files to port:**
- `Core/Discord/DiscordClient.cs` -> `core/discord/client.py`
- `Core/Utils/Http.cs` -> `core/utils/http.py`

### Phase 3: Export Core + PlainText/CSV/JSON Writers
- `ExportRequest` with path templating (`%g`, `%G`, `%c`, `%C`, etc.)
- `ExportContext` with member/channel/role caches
- `MessageWriter` ABC
- `PlainTextMessageWriter`, `CsvMessageWriter`, `JsonMessageWriter`
- `PartitionLimit` parsing and checking
- `MessageExporter` with partitioning logic
- `ChannelExporter` orchestrator

**Key source files to port:**
- `Core/Exporting/ExportRequest.cs` -> `core/exporting/request.py`
- `Core/Exporting/ExportContext.cs` -> `core/exporting/context.py`
- `Core/Exporting/MessageWriter.cs` -> `core/exporting/writers/base.py`
- `Core/Exporting/PlainTextMessageWriter.cs` -> `core/exporting/writers/plaintext.py`
- `Core/Exporting/CsvMessageWriter.cs` -> `core/exporting/writers/csv.py`
- `Core/Exporting/JsonMessageWriter.cs` -> `core/exporting/writers/json.py`
- `Core/Exporting/MessageExporter.cs` -> `core/exporting/message_exporter.py`
- `Core/Exporting/ChannelExporter.cs` -> `core/exporting/channel_exporter.py`

### Phase 4: Markdown Processing
- AST nodes (Text, Formatting, Heading, List, CodeBlock, Mention, Emoji, Link, Timestamp)
- `MarkdownParser` - port all regex matchers in exact priority order from C#
- `PlainTextMarkdownVisitor`
- `HtmlMarkdownVisitor`

**Key source files to port:**
- `Core/Markdown/Parsing/MarkdownParser.cs` -> `core/markdown/parser.py`
- `Core/Markdown/*.cs` -> `core/markdown/nodes.py`
- `Core/Markdown/Visiting/*Visitor.cs` -> `core/markdown/*_visitor.py`

### Phase 5: HTML Export
- Convert 3 Razor templates to Jinja2 (`preamble`, `message_group`, `postamble`)
- `HtmlMessageWriter` with message grouping (same author, <7min, no replies)
- Pre-process async data before rendering
- Theme dict (dark/light CSS variables)
- HTML minification
- Asset downloading (`ExportAssetDownloader` with SHA256 hash, keyed lock, CDN normalization)

**Key source files to port:**
- `Core/Exporting/PreambleTemplate.cshtml` -> `templates/html/preamble.html.j2`
- `Core/Exporting/MessageGroupTemplate.cshtml` -> `templates/html/message_group.html.j2`
- `Core/Exporting/PostambleTemplate.cshtml` -> `templates/html/postamble.html.j2`
- `Core/Exporting/HtmlMessageWriter.cs` -> `core/exporting/writers/html.py`
- `Core/Exporting/ExportAssetDownloader.cs` -> `core/exporting/asset_downloader.py`

### Phase 6: Filter DSL + CLI Wiring
- All filter types + combinators
- Recursive descent parser
- Wire up `export` and `exportall` commands with all options
- Parallel export with `asyncio.Semaphore`
- Rich progress display
- Thread fetching and inclusion

**Key source files to port:**
- `Core/Exporting/Filtering/*.cs` -> `core/exporting/filtering/`
- `Cli/Commands/Base/ExportCommandBase.cs` -> `cli/app.py`
- `Cli/Commands/ExportChannelsCommand.cs` -> `cli/app.py`
- `Cli/Commands/ExportAllCommand.cs` -> `cli/app.py`

### Phase 7: Tests + Polish
- Unit tests for Snowflake, models, markdown, filters, partition limits — COMPLETE (92 tests)
- Integration tests for export pipeline (Issue #17) — COMPLETE (27 tests)
  - MockDiscordClient with fixture data in `tests/conftest.py`
  - Full export tests for all 5 formats (PlainText, CSV, JSON, HTML Dark, HTML Light)
  - Partition rotation, message filtering, empty channel, forum channel rejection
  - 27 integration tests across 9 test classes in `tests/test_export_integration.py`
- Comprehensive unit tests for all untested modules (Issue #3) — COMPLETE (568 new tests)
  - `test_models.py` (226 tests) — All 14 Discord models, CDN URL builders, ExportFormat
  - `test_client.py` (118 tests) — DiscordClient, HTTP utils, Invite, asset downloader
  - `test_export_pipeline.py` (102 tests) — ExportContext, ExportRequest, MessageExporter, exceptions
  - `test_filters.py` (71 tests) — All filter is_match() methods, combinators, composed filters
  - `test_markdown_visitors.py` (51 tests) — HTML + plaintext markdown visitors
  - Total test suite: **687 tests**, all passing in ~0.5s
- README with usage, token setup, format docs, filter DSL docs — COMPLETE

---

## Verification

1. **Unit tests**: `pytest tests/` - 687 tests covering all models, client, pipeline, filters, visitors, parsers
2. **Manual test**: Run `discord-chat-exporter guilds -t <token>` to verify API connectivity
3. **Export test**: Export a known channel in all 5 formats, compare output structure against C# tool output
4. **Media test**: Run with `--media` flag, verify assets downloaded and referenced correctly in HTML
5. **Filter test**: Run with `--filter "from:username"` and `--filter "has:attachments"`, verify correct filtering
6. **Partition test**: Run with `--partition 10` and `--partition 1mb`, verify file splitting
