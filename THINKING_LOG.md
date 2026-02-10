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
