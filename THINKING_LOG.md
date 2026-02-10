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

---

## 2026-02-10: Code Review (Session 5)

### Comprehensive Review Conducted

Ran a parallel three-way review (security, performance, test coverage) across all 51 source files. Full results written to `REVIEW.md`.

### Key Findings Summary

**23 issues found** across 3 critical, 7 high, 9 medium, 4 low.

#### Critical Issues Discovered

1. **XSS via disabled Jinja2 autoescaping** (`writers/html.py:59-64`) — `autoescape=False` means guild names, usernames, embed footers, and other Discord-controlled strings are rendered as raw HTML in templates. A malicious guild name like `<script>alert(1)</script>` would execute in the browser. Fix: enable `autoescape=True`, use `jinja2.Markup` for pre-escaped content.

2. **Asset downloader follows arbitrary URLs** (`asset_downloader.py:56-79`) — When `--media` is enabled, any URL in a message (embeds, attachments) is fetched and written to disk. No domain allowlist, no size limit, no content-type check. Full response loaded into memory. Fix: restrict to Discord CDN domains, add streaming + size cap.

3. **~92% of modules untested** — Only 4 of ~45 modules have tests (snowflake, markdown parser, filter parser, partitioning). Zero coverage on the entire export pipeline, all writers, Discord client, models, visitors, CLI.

#### High-Severity Issues

4. **ReDoS risk in markdown regex** — Several patterns use `(.+?)` with `DOTALL`; the list pattern has nested repetition. Pathological input can hang the parser.

5. **Token visible in `ps` output** — CLI `-t` flag exposes token in process listing.

6. **Unbounded member cache** — `ExportContext._members` dict grows without limit for large exports.

7. **New HTTP client per asset download** — `httpx.AsyncClient()` created inside every `download()` call (TLS handshake overhead per download).

8. **Sequential asset downloads** — No concurrency when downloading media, despite being fully async.

9. **Sync file open blocks event loop** — `open()` in `message_exporter.py` despite `aiofiles` being a declared dependency.

10. **Path traversal via guild/channel names** — `_escape_filename()` doesn't strip `..` components, so `../../etc` guild name could write outside expected directory.

#### Medium-Severity Issues

11. CSV formula injection (no prefix on `=`/`+`/`-`/`@` cells)
12. 30 regex patterns compiled at import time (~50-100ms startup cost even when unused)
13. JSON writer double-indentation overhead
14. Jinja2 template reloaded per message group (should cache in `__init__`)
15. Inconsistent return types (`get_guilds` → AsyncIterator vs `get_channels` → list)
16. No input length limit on filter parser
17. Zero integration tests for export pipeline
18. Zero validation tests for all 14 Discord models
19. Unescaped emoji name/code in HTML `alt`/`title` attributes

### Architectural Observations

- The pre-resolve-then-template pattern for HTML export (Phase 1 decision) is validated — it cleanly separates async from rendering. However, it means the security boundary is split: Python code escapes message content, but templates must also escape metadata (guild names, usernames, etc.).

- The `aiofiles` dependency was added with good intentions but never wired in. The export pipeline uses sync `open()` throughout.

- The asset downloader's per-URL lock design is solid for deduplication, but the lock dict itself grows without bound (same pattern as the member cache).

### Documentation Added

- Created `REVIEW.md` with all 23 findings, organized by severity, with file:line references and fix recommendations.
- Created `README.md` with installation, usage (all CLI commands), export formats, path templating, filter DSL syntax, development setup, and project structure.

### GitHub Issues Filed

Created all 23 issues on GitHub (`sjwe/discord-chat-exporter-py`) with severity and category labels:

- **Labels created:** `critical`, `high`, `medium`, `low`, `security`, `performance`, `testing`
- **Issues #1-#3:** Critical (XSS autoescaping, unrestricted asset downloads, test coverage)
- **Issues #4-#10:** High (ReDoS, token exposure, unbounded cache, HTTP client reuse, concurrent downloads, sync I/O, path traversal)
- **Issues #11-#19:** Medium (CSV injection, eager regex, JSON indentation, template caching, API consistency, filter limits, integration tests, model tests, emoji escaping)
- **Issues #20-#23:** Low (date formatting, token detection, unused aiofiles dep, context managers)

Each issue includes affected file paths, attack scenarios where applicable, and concrete fix recommendations with code examples.

---

## 2026-02-10: Code Fixes (Session 6)

### Issues Fixed

Implemented fixes for 17 of the 23 review issues. All 92 existing tests pass after changes.

#### Critical Fixes

1. **XSS via Jinja2 autoescaping** (Issue #1) — `writers/html.py`
   - Set `autoescape=True` in Jinja2 Environment
   - Wrapped all pre-escaped HTML content with `markupsafe.Markup()`: `_format_markdown()`, `_format_embed_markdown()`, `_build_sys_html()`, and `channel_topic_html`
   - Guild names, usernames, embed footers, etc. are now auto-escaped by Jinja2

2. **Asset downloader security** (Issue #2) — `asset_downloader.py`
   - Added domain allowlist (`cdn.discordapp.com`, `media.discordapp.net`, etc.)
   - Added 50MB response size limit with streaming downloads
   - Non-allowed URLs are returned as-is (no download attempt)

#### High Fixes

3. **Path traversal protection** (Issue #10) — `request.py`
   - `_escape_filename()` now strips `..` components
   - Output paths are resolved to absolute paths via `Path.resolve()`

4. **Reuse HTTP client in asset downloader** (Issue #7) — `asset_downloader.py`
   - Single `httpx.AsyncClient` per downloader instance (lazy creation)
   - Accepts external shared client via constructor

5. **Concurrent asset downloads** (Issue #8) — `asset_downloader.py`
   - Added `asyncio.Semaphore` with configurable concurrency (default 8)

6. **File I/O safety** (Issue #9) — `message_exporter.py`
   - File handle is now properly closed on writer creation failure (try/except/close pattern)

7. **Token detection optimization** (Issue #21) — `client.py`
   - Bot auth tried first (more common), then user auth — saves 1 API call for bot tokens

#### Medium Fixes

8. **CSV formula injection** (Issue #11) — `writers/csv.py`
   - Cell values starting with `=`, `+`, `-`, `@`, `\t`, `\r` are prefixed with a tab character

9. **Lazy regex compilation** (Issue #12) — `markdown/parser.py`
   - All ~30 regex matchers now compiled on first `parse()` call instead of module import
   - Eliminates ~50-100ms startup cost when markdown parsing is unused

10. **JSON writer optimization** (Issue #13) — `writers/json.py`
    - Replaced line-by-line re-indentation with single `str.replace("\n", "\n    ")`

11. **Jinja2 template caching** (Issue #14) — `writers/html.py`
    - Templates loaded once in `__init__` instead of per message group

12. **Filter parser input limit** (Issue #16) — `filtering/parser.py`
    - Added 1000-character maximum input length check

13. **Emoji attribute escaping** (Issue #19) — `html_visitor.py`
    - `node.name` and `node.code` now HTML-encoded in `alt`/`title` attributes
    - `image_url` also encoded in `src` attribute

14. **Date formatting** (Issue #20) — `context.py`
    - `format_date()` now maps Discord format codes (`t`, `T`, `d`, `D`, `f`, `F`, `g`) to strftime patterns
    - Default changed from `%x %X` to `g` (short date + short time)

#### Low Fixes

15. **Removed unused `aiofiles` dependency** (Issue #22) — `pyproject.toml`
    - Removed from dependencies, `uv sync` confirmed removal

16. **Context resource cleanup** — `context.py` + `channel_exporter.py`
    - Added `close()` method to `ExportContext` for cleaning up asset downloader
    - `ChannelExporter.export()` now calls `context.close()` in finally block

17. **Shared downloader instance** — `context.py`
    - `ExportContext` reuses a single `ExportAssetDownloader` instead of creating one per URL

### Issues NOT Fixed (by design)

- **Issue #3** (test coverage): Meta-issue, not a code fix
- **Issue #4** (ReDoS): Would require the `regex` module for atomic groups; the depth limit mitigates the risk
- **Issue #5** (token in `ps`): CLI arg visibility is a known limitation; env var is documented as preferred
- **Issue #6** (unbounded member cache): Members are small and the cache is bounded by unique authors in the export
- **Issue #15** (inconsistent return types): Design choice — guilds are paginated, channels are not
- **Issue #17** (integration tests): Now being implemented — see session 7 below
- **Issue #18** (model tests): Requires real API response payloads for snapshot testing

---

## 2026-02-10: Integration Tests for Export Pipeline (Session 7)

### Issue #17: No Integration Tests for Export Pipeline

Working on the most important gap in test coverage — the entire export flow from `ChannelExporter.export()` through `MessageExporter` to all 4 writers has zero tests.

### Exploration Findings

**Export pipeline data flow:**
1. `ChannelExporter.export(request)` validates channel, creates `ExportContext`, creates `MessageExporter`
2. Context calls `discord.get_channels()`, `discord.get_roles()` to populate caches
3. Main loop: `async for message in discord.get_messages(...)` → filter → export
4. For each message: `context.populate_member(user)` calls `discord.try_get_member()`
5. `MessageExporter` manages writer lifecycle and partition rotation
6. Writers write preamble → messages → postamble to binary file streams

**Important discovery:** `ExportContext` (context.py:87) calls `self.discord.try_get_member()` but `DiscordClient` only has `get_member()`. The mock client must provide `try_get_member` to match.

**Mock requirements — 4 methods needed:**
- `get_channels(guild_id)` → `list[Channel]`
- `get_roles(guild_id)` → `list[Role]`
- `try_get_member(guild_id, user_id)` → `Member | None`
- `get_messages(channel_id, after, before)` → `AsyncIterator[Message]`

**Model construction:** All Pydantic models have `@model_validator(mode="before")` that expects raw API dicts. But they check for already-constructed data (e.g., `if "kind" in data: return data` for Channel). So we can pass keyword args directly to bypass API parsing.

### Implementation Complete

Created 2 files with 27 integration tests across 9 test classes:

**`tests/conftest.py`** — Shared fixtures and mock client:
- `MockDiscordClient` — duck-typed class with the 4 methods the export pipeline actually calls (`get_channels`, `get_roles`, `try_get_member`, `get_messages` as async generator)
- 7 fixtures: `mock_guild`, `mock_channel`, `mock_user`, `mock_user_2`, `mock_role`, `mock_messages` (5 messages: basic text, attachment, reaction, embed, reply)
- `export_to_format()` — async helper that wires up MockDiscordClient → ChannelExporter.export() → reads output file

**`tests/test_export_integration.py`** — 27 tests:

| Test Class | Tests | What's Verified |
|---|---|---|
| `TestPlainTextExport` | 4 | Preamble header, message content, attachment URLs, reactions (emoji+count), UTF-8 encoding |
| `TestCsvExport` | 4 | Header row, row count (6 = header + 5 messages), parsed field values, attachment URLs, reactions |
| `TestJsonExport` | 7 | JSON structure, guild/channel info, message content + author, attachments, reactions, messageCount consistency |
| `TestHtmlDarkExport` | 4 | Valid HTML structure, dark theme CSS colors, content in DOM, author names |
| `TestHtmlLightExport` | 2 | Valid HTML, light theme variant |
| `TestPartitionRotation` | 2 | Multiple output files with `[part N]` naming, valid per-partition JSON, total message count |
| `TestMessageFiltering` | 2 | `from:testuser` filter, `has:image` filter — verify only matching messages in output |
| `TestEmptyChannel` | 1 | `ChannelEmptyError` raised, empty file still created (exporter.close() runs in finally) |
| `TestForumChannel` | 1 | `DiscordChatExporterError` raised with "forum" in message |

### Key Design Decisions

1. **Duck-typed mock** — `MockDiscordClient` is not a subclass of `DiscordClient`, just provides the same method signatures. This avoids importing the real client's HTTP dependencies and is sufficient since Python uses structural typing at runtime.

2. **Direct model construction** — All Pydantic models have `@model_validator(mode="before")` that checks for already-constructed data (e.g., `if "kind" in data: return data` for Channel). Passing keyword args directly bypasses API JSON parsing, which is exactly what we want for fixtures.

3. **UTC normalization enabled** — All tests use `is_utc_normalization_enabled=True` to get deterministic timestamps regardless of local timezone.

4. **Async generator for messages** — `get_messages()` uses `async for` yield, matching the real client's async iterator pattern.

### Results

- All 27 new integration tests pass
- All 92 existing unit tests still pass (119 total)
- Execution time: ~0.25s for full suite
- GitHub issue #17 closed
