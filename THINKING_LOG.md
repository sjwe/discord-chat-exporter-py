# Thinking Log: DiscordChatExporter C# -> Python Conversion

## 2026-02-10: Initial Analysis & Planning

### Source Codebase Assessment

Explored the C# DiscordChatExporter project thoroughly. Key findings:

**Architecture:**
- 3-layer solution: CLI (CliFx), Core (domain + API + export), GUI (Avalonia)
- We only need CLI + Core. GUI is skipped entirely.
- Well-separated concerns: Discord API client, domain models, export writers, markdown processing, message filtering

**Scale of the project:**
- ~50+ C# source files across Core + CLI
- 12+ domain model types with complex JSON parsing
- 15+ Discord API endpoints with pagination
- 5 export format writers
- Full Discord markdown parser with 30+ regex matchers
- Message filter DSL with boolean expression support
- 3 Razor HTML templates (preamble ~500 lines CSS/JS, message group ~676 lines, postamble)

### Key Technical Decisions Made

**Why Pydantic v2 over dataclasses:**
- Every C# model has a `Parse(JsonElement json)` static factory that manually extracts JSON fields
- Pydantic's `model_validate()` with `alias` and `@model_validator` handles this automatically
- Trade-off: ~2MB dependency overhead, slightly slower imports. Acceptable for a CLI tool.

**Why frozen dataclass for Snowflake (not Pydantic):**
- Snowflake is used as dict keys and in sets throughout the codebase
- Needs `__hash__`, `__eq__`, `__lt__` with custom semantics
- Pydantic models are hashable with `frozen=True` but the overhead isn't justified for a simple int wrapper

**Why click over typer:**
- Need custom parameter types: Snowflake (accepts both int IDs and ISO dates), PartitionLimit (accepts "100" or "10mb"), ExportFormat
- Click has first-class `ParamType` support; typer is a thin wrapper that makes this harder
- Click is also the more mature, well-documented option

**Why hand-rolled filter parser over lark:**
- The grammar is tiny: 6 filter types, 3 boolean operators, parentheses, quoting
- A recursive descent parser is ~120 lines of Python
- Adding lark as a dependency for this is overkill
- Easier to debug and maintain

**Why pre-resolve async for HTML templates:**
- The C# Razor templates call `await ResolveAssetUrlAsync()` and `await FormatMarkdownAsync()` inline
- Jinja2 does not support async calls in templates
- Jinja2 has an `enable_async` mode but it's limited and doesn't help with arbitrary coroutines
- Solution: Build a `MessageRenderData` object with all URLs resolved and markdown pre-formatted before passing to Jinja2
- This actually improves separation of concerns vs the C# approach

### Discord API Details Worth Noting

**Authentication quirk:** Token type (user vs bot) is auto-detected by trying user auth first, falling back to bot. User tokens go as raw `Authorization: <token>`, bot tokens as `Authorization: Bot <token>`.

**Pagination pattern:** Messages fetched with `after` cursor (Snowflake ID), batch size 100, forward chronologically, then reversed before yielding. This is important to replicate exactly.

**Rate limiting implementation:**
- Advisory: `X-RateLimit-Remaining` and `X-RateLimit-Reset-After` headers
- Hard: HTTP 429 with `Retry-After` header
- Configurable respect levels (ignore all, respect for user only, respect for bot only, respect all)
- Max wait capped at 60 seconds
- C# uses Polly with exponential backoff: `2^attempt + 1` seconds, max 8 retries

**Thread fetching diverges by token type:**
- User tokens: `GET /channels/{id}/threads/search` with offset pagination
- Bot tokens: `GET /guilds/{id}/threads/active` + `GET /channels/{id}/threads/archived/{type}`
- This is because Discord exposes different endpoints depending on auth type

### HTML Export Complexity

The HTML export is by far the most complex part. The Razor templates contain:

1. **PreambleTemplate.cshtml** (~500+ lines):
   - Full CSS with theme-parameterized colors (dark/light)
   - JavaScript for highlight.js, Lottie animation, spoiler handling, message scroll-to
   - SVG icon definitions for 20+ Discord system message types
   - Font face declarations
   - Guild/channel metadata header

2. **MessageGroupTemplate.cshtml** (~676 lines):
   - System notification rendering for all MessageKind values (join, leave, pin, call, etc.)
   - Regular message rendering with avatar, author, timestamp, edited indicator
   - Reply/interaction rendering with referenced message preview
   - Attachment rendering (image, video, audio, generic file) with size/dimensions
   - Embed rendering: Spotify player, YouTube player, generic image/video/gifv, rich embeds with fields
   - Sticker rendering (PNG, APNG, Lottie)
   - Reaction rendering with emoji images and counts
   - Invite embed rendering

3. **PostambleTemplate.cshtml** (small):
   - Message count, export date, timezone info

**Strategy:** Copy CSS/JS verbatim from the C# templates. Convert the Razor control flow to Jinja2 syntax. The visual output must match.

### Asset Download Details

- Files named with SHA256 hash (first 5 chars) of normalized URL + original filename
- Discord CDN URL normalization: strip `ex`, `is`, `hm` query parameters (these are expiring signatures)
- Per-URL `asyncio.Lock` to prevent concurrent downloads of same file
- "Reuse" mode checks if file already exists on disk before downloading

### Markdown Parser Architecture

The C# parser uses an ordered list of regex matchers processed with priority. Each matcher:
1. Tries to match at the current position
2. If matched, creates an AST node and advances the cursor
3. If no matcher matches, creates a TextNode for one character and advances

Key quirk: The `¯\_(ツ)_/¯` kaomoji is handled as a special case before escape processing, since the backslash would otherwise be consumed as an escape character.

Recursion depth is limited to 32 to prevent stack overflow on deeply nested markdown.

### What We're NOT Porting

- GUI (Avalonia desktop app) - out of scope
- Data package import (`--data-package <zip>`) - niche feature, can add later
- `--fuck-russia` / Ukraine support message - not relevant to the Python port
- YoutubeExplode integration - the C# tool uses this to resolve YouTube metadata for embeds; we can skip this or use a lighter approach

### Risk Assessment

**Highest risk:** HTML export fidelity. The templates are large and contain many edge cases. Plan to do visual comparison testing against C# output.

**Medium risk:** Markdown parser parity. The regex matchers must be in the exact same order and handle the same edge cases. Comprehensive test suite needed.

**Low risk:** API client, domain models, CSV/JSON/PlainText writers. These are straightforward translations.

### Open Questions Resolved

- **Scope:** CLI only, no GUI/TUI
- **Python version:** 3.12+
- **Build tool:** uv

---

## 2026-02-10: Implementation Progress (Session 2)

### Phase 1: Foundation - COMPLETE

Created the full package structure and all foundational modules:

- **pyproject.toml** - uv project config with all deps, entry point `discord-chat-exporter`
- **Snowflake** (`core/discord/snowflake.py`) - Frozen, hashable, comparable. Supports parse from int or ISO date. `ZERO` class attribute for DM sentinel.
- **ImageCdn** (`core/discord/models/cdn.py`) - All Discord CDN URL builders ported (guild icons, user avatars, emoji, stickers, etc.)
- **ExportFormat** (`core/exporting/format.py`) - Enum with file_extension, display_name, is_html properties

### Phase 1 continued: All Pydantic Domain Models - COMPLETE

Ported all 15+ C# data models to Pydantic v2 with `@model_validator(mode="before")` for API JSON parsing:

| Model | Key Design Notes |
|-------|-----------------|
| Guild | `DIRECT_MESSAGES` class-level singleton, `is_direct` property |
| Channel | ChannelKind enum, parent chain navigation, hierarchical name |
| User | Discriminator handling (old/new system), avatar fallback logic |
| Member | `create_fallback()` for users who left, guild-specific avatars |
| Message | MessageKind/MessageFlags enums, embed normalization (Twitter multi-image), `get_referenced_users()` iterator |
| Attachment | File type detection via extension sets, spoiler detection |
| Embed + sub-models | EmbedKind enum, projection classes (Spotify/YouTube/Twitch) |
| Emoji | Lazy code lookup via emoji_index, custom vs standard detection |
| Reaction, Role, Sticker, Interaction, MessageReference | Straightforward ports |

### Phase 2: Discord API Client - COMPLETE (via agent)

- **HTTP utils** (`core/utils/http.py`) - tenacity retry decorator with custom wait function reading `Retry-After` headers, exponential backoff `2^attempt + 1`, 8 max attempts
- **DiscordClient** (`core/discord/client.py`) - Full async client with all endpoints:
  - Token auto-detection (user vs bot)
  - Rate limiting with `X-RateLimit-Remaining`/`X-RateLimit-Reset-After`
  - All endpoints: guilds, channels, threads, messages (paginated async gen), members, roles, DMs, invites, reactions
  - Proper error handling (401/403/404 → meaningful exceptions)

### Phase 3: Export Core - COMPLETE

- **ExportRequest** (`core/exporting/request.py`) - Path templating (%g, %G, %c, %C, etc.), default filename generation, directory vs file output detection
- **ExportContext** (`core/exporting/context.py`) - Member/channel/role caches, date formatting, asset URL resolution, fallback content for system notifications
- **PartitionLimit** (`core/exporting/partitioning.py`) - Parse "10mb"/"500kb"/"100" formats, file size and message count limits
- **MessageExporter** (`core/exporting/message_exporter.py`) - Partition management, writer lifecycle
- **ChannelExporter** (`core/exporting/channel_exporter.py`) - Orchestrator: validates channel, populates caches, iterates messages, applies filters
- **AssetDownloader** (`core/exporting/asset_downloader.py`) - SHA256-based filenames, per-URL locks, reuse support
- **Writers**: PlainText, CSV, JSON all complete with full feature parity

### Phase 4: Markdown Processing - COMPLETE (via agent)

- **AST Nodes** (`core/markdown/nodes.py`) - All node types as frozen dataclasses: Text, Formatting, Heading, List, CodeBlock, Link, Mention, Emoji, Timestamp
- **Parser** (`core/markdown/parser.py`) - ~700 lines, regex-based matching in priority order, `parse()`, `parse_minimal()`, `extract_emojis()`, `extract_links()`
- **Base Visitor** (`core/markdown/visitor.py`) - Async visitor with dispatch by node type
- **PlainTextMarkdownVisitor** (`core/markdown/plaintext_visitor.py`) - Strips formatting, resolves mentions/channels/roles to display names
- **HtmlMarkdownVisitor** (`core/markdown/html_visitor.py`) - Full HTML rendering: formatting tags, spoilers, code blocks, mentions with colors, emoji images, timestamps, Discord message links with scroll-to

### Phase 5: HTML Export - COMPLETE

### Phase 6: Filter DSL - COMPLETE (via agent)

- **MessageFilter ABC + NullMessageFilter** (`filtering/base.py`)
- **5 filter types** (`filtering/filters.py`) - Contains (word-boundary), From, Has (link/embed/file/video/image/sound/pin/invite), Mentions, Reaction
- **Combinators** (`filtering/combinators.py`) - BinaryExpression (AND/OR), Negated (NOT)
- **Recursive descent parser** (`filtering/parser.py`) - Handles prefixed filters, bare text, quoted strings, operators (&, |, -, ~), parentheses, implicit AND

### Phase 7: CLI - COMPLETE (skeleton)

- All commands wired up: guilds, channels, dm, export, exportall, exportdm
- Custom Click param types: SnowflakeParamType, ExportFormatParamType
- All export options: --output, --format, --after, --before, --partition, --filter, --media, --threads, --parallel

---

## 2026-02-10: Implementation Progress (Session 3)

### Phase 5: HTML Export - COMPLETE

All missing pieces implemented:

- **Emoji Index** (`core/discord/models/emoji_index.py`) - Auto-generated from C# EmojiIndex.cs via regex extraction script. 3,538 entries in `EMOJI_TO_CODE` (emoji char → shortcode), 5,291 entries in `CODE_TO_EMOJI` (shortcode → emoji char). Total 8,838 lines.

- **HtmlMessageWriter** (`core/exporting/writers/html.py`) - Full port from C# `HtmlMessageWriter.cs`:
  - Message grouping logic: same author, <7min gap, no replies, matching system/normal type
  - Pre-resolves ALL async data before passing to Jinja2 templates (design decision from Phase 1)
  - `_prepare_message()` builds a flat dict with all pre-resolved URLs, formatted HTML, author colors, reply data, attachments, embeds, stickers, reactions
  - `_prepare_embed()` handles all 6 embed types: Spotify, YouTube, image, video, gifv, rich
  - `_build_sys_html()` generates HTML for all system notification types (join, leave, call, pin, name change, etc.)
  - `_make_themed()` creates a dark/light value selector function passed to templates

- **Jinja2 Templates** (3 files in `templates/html/`):
  - `preamble.html.j2` (~750 lines) - Full CSS with `{{ themed() }}` calls for dark/light colors, highlight.js + lottie.js scripts, SVG icon defs, guild/channel header. Verbatim port of PreambleTemplate.cshtml.
  - `message_group.html.j2` (~250 lines) - All message rendering: system notifications, regular messages with headers, reply references (message/interaction/deleted), attachments (image/video/audio/generic with spoiler support), all embed types (spotify/youtube/image/video/gifv/rich with fields/footer/thumbnail/images), stickers (image/lottie), reactions.
  - `postamble.html.j2` (~10 lines) - Close chatlog div, message count, timezone.

- **Package Installation** - `uv sync` successful. Fixed `pyproject.toml` readme field (was referencing missing README.md). All 35 packages installed including pydantic, httpx, click, jinja2, rich, tenacity, aiofiles, plus dev deps (pytest, ruff, mypy).

### Design Notes for HTML Export

**Template data flow:** Python writer → flat dicts → Jinja2 templates. Each message becomes a dict like:
```python
{
    "id": "123456789",
    "is_first": True,
    "author_display_name": "User",
    "author_color": "rgb(255, 0, 0)",  # pre-converted from hex
    "content_html": "<strong>bold</strong>",  # pre-formatted markdown
    "reply": {"kind": "message", "html": "...", ...},  # or None
    "attachments": [{"url": "...", "is_image": True, ...}],
    "embeds": [{"type": "rich", "title_html": "...", ...}],
    ...
}
```

**Themed CSS:** Rather than duplicating the entire CSS, the `themed()` function is passed to templates and called inline: `background-color: {{ themed("#36393e", "#ffffff") }};`. This matches the C# `@Themed()` pattern 1:1.

**Skipped for now:** Invite embed rendering (requires Discord API calls during template rendering - can be added later). The C# template extracts invite codes from links and fetches invite metadata.

---

## 2026-02-10: Verification & Fixes (Session 4)

### Import Chain Fix: Snowflake Pydantic Integration

All models using `Snowflake` as a field type failed at import time:
```
PydanticSchemaGenerationError: Unable to generate pydantic-core schema for Snowflake
```

**Fix:** Added `__get_pydantic_core_schema__` classmethod to `Snowflake` class:
- Accepts `Snowflake`, `int`, or `str` inputs
- Serializes as raw int value
- Uses `pydantic_core.core_schema.no_info_plain_validator_function`

### Verification Results

- All module imports: PASS (all writers, client, models, markdown, filters)
- CLI smoke test: PASS (`discord-chat-exporter --help` shows all 6 commands)
- Emoji index: PASS (3,538 emoji→code, 5,291 code→emoji)

### Cleanup

- Removed `parse_emoji_index.py` (one-time generation script)
- Removed `tests/test_generate_emoji_index.py` (not a real test)

### Unit Test Suite - 92 tests, all passing

Wrote comprehensive tests across 4 files:

- **`tests/test_snowflake.py`** (16 tests) - Value access, str/int/repr/bool, hashing, equality, ordering, ZERO sentinel, timestamp extraction, from_date roundtrip, parsing (int string, ISO date, invalid), Pydantic integration (from Snowflake/int/str, serialization)

- **`tests/test_partitioning.py`** (11 tests) - Parse MB/GB/KB/B, case insensitivity, spaces, decimals (1.5gb), message count, invalid input, null limit

- **`tests/test_filter_parser.py`** (26 tests) - All 5 filter types (from/mentions/reaction/has/contains), quoted strings, implicit AND, explicit AND/OR, negation (-/~), grouped expressions, negated groups, three-term chaining, empty/whitespace errors, case-insensitive prefixes, escaped quotes, unterminated quotes, has:invalid fallback to contains

- **`tests/test_markdown_parser.py`** (39 tests) - Plain text, empty string, all formatting kinds (bold, italic ×2, underline, strikethrough, spoiler, bold-italic, mixed), inline/multiline code blocks (with/without language), all mention types (user, user!, channel, role, @everyone, @here), custom/animated emoji, extract_emojis, auto-links, masked links, extract_links, headings (h1/h3 with required trailing newline), quotes, unordered lists, timestamps (basic, format "f", relative "R"→None), shrug kaomoji preservation, parse_minimal (mentions only, no formatting)

### Test findings that revealed parser behavior

- **Headings** require `^` anchor + trailing `\n` — `# Heading` alone doesn't parse, need `# Heading\n`
- **`has:invalid_kind`** doesn't error — parser backtracks and treats entire string as `ContainsMessageFilter`
- **Timestamp format `R`** (relative) is intentionally stored as `None` since relative time doesn't make sense in static exports

### Remaining Work

1. **End-to-end test** - Export a real channel with a test token to verify output correctness
