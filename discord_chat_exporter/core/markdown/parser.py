"""Regex-based Discord markdown parser.

Discord does NOT use a recursive-descent parser for markdown which becomes
evident in some scenarios, like when multiple formatting nodes are nested
together.  To replicate Discord's behaviour we employ a set of regular
expressions that are executed sequentially in a first-matched-first-served
manner.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Sequence

from discord_chat_exporter.core.discord.snowflake import Snowflake
from discord_chat_exporter.core.markdown.nodes import (
    EmojiNode,
    FormattingKind,
    FormattingNode,
    HeadingNode,
    InlineCodeBlockNode,
    LinkNode,
    ListItemNode,
    ListNode,
    MarkdownNode,
    MentionKind,
    MentionNode,
    MultiLineCodeBlockNode,
    TextNode,
    TimestampNode,
    TIMESTAMP_INVALID,
    get_children,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_MAX_DEPTH = 32


@dataclass(frozen=True)
class _Segment:
    """A view into the original source string."""

    source: str
    start: int
    length: int

    @property
    def end(self) -> int:
        return self.start + self.length

    def relocate(self, new_start: int, new_length: int) -> _Segment:
        return _Segment(self.source, new_start, new_length)

    def __str__(self) -> str:
        return self.source[self.start : self.end]


@dataclass(frozen=True)
class _ParsedMatch:
    segment: _Segment
    value: MarkdownNode


# Matcher: callable that takes (depth, segment) -> Optional[_ParsedMatch]
_Matcher = Callable[[int, _Segment], _ParsedMatch | None]


def _regex_matcher(
    pattern: re.Pattern[str],
    transform: Callable[[int, _Segment, re.Match[str]], MarkdownNode | None],
) -> _Matcher:
    """Build a matcher from a compiled regex and a transform function."""

    def _match(depth: int, segment: _Segment) -> _ParsedMatch | None:
        m = pattern.search(segment.source, segment.start, segment.end)
        if m is None:
            return None
        # The C# code does a second check: ensure the match is valid when
        # considering the substring up to segment.end (to properly anchor ^/$).
        # Python's re.search with pos/endpos already respects ^/$ with MULTILINE
        # so this is generally handled, but we double-check by verifying the match
        # falls within our segment.
        if m.start() < segment.start or m.end() > segment.end:
            return None

        seg_match = segment.relocate(m.start(), m.end() - m.start())
        node = transform(depth, seg_match, m)
        if node is None:
            return None
        return _ParsedMatch(seg_match, node)

    return _match


def _string_matcher(
    needle: str,
    transform: Callable[[_Segment], MarkdownNode],
) -> _Matcher:
    """Build a matcher that looks for an exact substring."""

    def _match(depth: int, segment: _Segment) -> _ParsedMatch | None:
        idx = segment.source.find(needle, segment.start, segment.end)
        if idx < 0:
            return None
        seg_match = segment.relocate(idx, len(needle))
        return _ParsedMatch(seg_match, transform(seg_match))

    return _match


def _aggregate_matcher(matchers: Sequence[_Matcher]) -> _Matcher:
    """Build a matcher that tries all sub-matchers and returns the earliest hit."""

    def _match(depth: int, segment: _Segment) -> _ParsedMatch | None:
        earliest: _ParsedMatch | None = None
        for matcher in matchers:
            hit = matcher(depth, segment)
            if hit is None:
                continue
            if earliest is None or hit.segment.start < earliest.segment.start:
                earliest = hit
            if earliest.segment.start == segment.start:
                break
        return earliest

    return _match


def _match_all(
    matcher: _Matcher,
    depth: int,
    segment: _Segment,
) -> list[MarkdownNode]:
    """Apply *matcher* across *segment*, filling gaps with TextNodes."""
    results: list[MarkdownNode] = []
    current = segment.start
    while current < segment.end:
        hit = matcher(depth, segment.relocate(current, segment.end - current))
        if hit is None:
            break
        if hit.segment.start > current:
            results.append(TextNode(segment.source[current : hit.segment.start]))
        results.append(hit.value)
        current = hit.segment.start + hit.segment.length
    if current < segment.end:
        results.append(TextNode(segment.source[current : segment.end]))
    return results


# ---------------------------------------------------------------------------
# Recursive parse helpers
# ---------------------------------------------------------------------------


def _parse(
    depth: int,
    segment: _Segment,
    matcher: _Matcher,
) -> list[MarkdownNode]:
    if depth >= _MAX_DEPTH:
        return [TextNode(str(segment))]
    return _match_all(matcher, depth + 1, segment)


def _seg_from_group(segment: _Segment, m: re.Match[str], group: int) -> _Segment:
    """Create a _Segment pointing at a regex match group."""
    return segment.relocate(m.start(group), m.end(group) - m.start(group))


# ---------------------------------------------------------------------------
# Regex flags
# ---------------------------------------------------------------------------

# VERBOSE + MULTILINE is the Python equivalent of the C# defaults
_BASE = re.VERBOSE | re.MULTILINE
_BASE_S = _BASE | re.DOTALL


# ---------------------------------------------------------------------------
# Matchers – formatting
# ---------------------------------------------------------------------------


def _mk_bold() -> _Matcher:
    pat = re.compile(r"\*\*(.+?)\*\*(?!\*)", _BASE_S)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        return FormattingNode(FormattingKind.BOLD, _parse(d, _seg_from_group(s, m, 1), _NODE_MATCHER))

    return _regex_matcher(pat, _t)


def _mk_italic() -> _Matcher:
    pat = re.compile(r"\*(?!\s)(.+?)(?<!\s|\*)\*(?!\*)", _BASE_S)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        return FormattingNode(FormattingKind.ITALIC, _parse(d, _seg_from_group(s, m, 1), _NODE_MATCHER))

    return _regex_matcher(pat, _t)


def _mk_italic_bold() -> _Matcher:
    pat = re.compile(r"\*(\*\*.+?\*\*)\*(?!\*)", _BASE_S)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        return FormattingNode(
            FormattingKind.ITALIC,
            _parse(d, _seg_from_group(s, m, 1), _BOLD_MATCHER),
        )

    return _regex_matcher(pat, _t)


def _mk_italic_alt() -> _Matcher:
    pat = re.compile(r"_(.+?)_(?!\w)", _BASE_S)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        return FormattingNode(FormattingKind.ITALIC, _parse(d, _seg_from_group(s, m, 1), _NODE_MATCHER))

    return _regex_matcher(pat, _t)


def _mk_underline() -> _Matcher:
    pat = re.compile(r"__(.+?)__(?!_)", _BASE_S)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        return FormattingNode(FormattingKind.UNDERLINE, _parse(d, _seg_from_group(s, m, 1), _NODE_MATCHER))

    return _regex_matcher(pat, _t)


def _mk_italic_underline() -> _Matcher:
    pat = re.compile(r"_(__.+?__)_(?!_)", _BASE_S)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        return FormattingNode(
            FormattingKind.ITALIC,
            _parse(d, _seg_from_group(s, m, 1), _UNDERLINE_MATCHER),
        )

    return _regex_matcher(pat, _t)


def _mk_strikethrough() -> _Matcher:
    pat = re.compile(r"~~(.+?)~~", _BASE_S)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        return FormattingNode(FormattingKind.STRIKETHROUGH, _parse(d, _seg_from_group(s, m, 1), _NODE_MATCHER))

    return _regex_matcher(pat, _t)


def _mk_spoiler() -> _Matcher:
    pat = re.compile(r"\|\|(.+?)\|\|", _BASE_S)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        return FormattingNode(FormattingKind.SPOILER, _parse(d, _seg_from_group(s, m, 1), _NODE_MATCHER))

    return _regex_matcher(pat, _t)


def _mk_single_line_quote() -> _Matcher:
    pat = re.compile(r"^>\s(.+\n?)", _BASE)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        return FormattingNode(FormattingKind.QUOTE, _parse(d, _seg_from_group(s, m, 1), _NODE_MATCHER))

    return _regex_matcher(pat, _t)


def _mk_repeated_single_line_quote() -> _Matcher:
    pat = re.compile(r"(?:^>\s(.*\n?)){2,}", _BASE)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        # m.groups() only returns the last capture; we need all captures.
        # Use finditer on the content to grab each line.
        children: list[MarkdownNode] = []
        line_pat = re.compile(r"^>\s(.*\n?)", re.MULTILINE)
        for lm in line_pat.finditer(s.source, m.start(), m.end()):
            seg = s.relocate(lm.start(1), lm.end(1) - lm.start(1))
            children.extend(_parse(d, seg, _NODE_MATCHER))
        return FormattingNode(FormattingKind.QUOTE, children)

    return _regex_matcher(pat, _t)


def _mk_multi_line_quote() -> _Matcher:
    pat = re.compile(r"^>>>\s(.+)", _BASE_S)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        return FormattingNode(FormattingKind.QUOTE, _parse(d, _seg_from_group(s, m, 1), _NODE_MATCHER))

    return _regex_matcher(pat, _t)


def _mk_heading() -> _Matcher:
    pat = re.compile(r"^(\#{1,3})\s(.+)\n", _BASE)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        level = m.end(1) - m.start(1)
        return HeadingNode(level, _parse(d, _seg_from_group(s, m, 2), _NODE_MATCHER))

    return _regex_matcher(pat, _t)


def _mk_list() -> _Matcher:
    pat = re.compile(r"^(\s*)(?:[\-\*]\s(.+(?:\n\s\1.*)*)?\n?)+", _BASE)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        # Extract all captures from group 2 (list items)
        items: list[ListItemNode] = []
        # Python re doesn't expose multiple captures of repeated groups.
        # Re-parse each list item within the matched region.
        item_pat = re.compile(r"[\-\*]\s(.+(?:\n\s" + re.escape(m.group(1)) + r".*)*)", re.MULTILINE)
        for item_m in item_pat.finditer(s.source, m.start(), m.end()):
            seg = s.relocate(item_m.start(1), item_m.end(1) - item_m.start(1))
            items.append(ListItemNode(_parse(d, seg, _NODE_MATCHER)))
        return ListNode(items)

    return _regex_matcher(pat, _t)


# ---------------------------------------------------------------------------
# Matchers – code blocks
# ---------------------------------------------------------------------------


def _mk_inline_code_block() -> _Matcher:
    pat = re.compile(r"(`{1,2})([^`]+)\1", _BASE_S)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        return InlineCodeBlockNode(m.group(2))

    return _regex_matcher(pat, _t)


def _mk_multi_line_code_block() -> _Matcher:
    pat = re.compile(r"```(?:(\w*)\n)?(.+?)```", _BASE_S)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        lang = m.group(1) or ""
        code = m.group(2).strip("\r\n")
        return MultiLineCodeBlockNode(lang, code)

    return _regex_matcher(pat, _t)


# ---------------------------------------------------------------------------
# Matchers – mentions
# ---------------------------------------------------------------------------


def _mk_everyone_mention() -> _Matcher:
    return _string_matcher("@everyone", lambda s: MentionNode(None, MentionKind.EVERYONE))


def _mk_here_mention() -> _Matcher:
    return _string_matcher("@here", lambda s: MentionNode(None, MentionKind.HERE))


def _mk_user_mention() -> _Matcher:
    pat = re.compile(r"<@!?(\d+)>", _BASE)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        return MentionNode(Snowflake.try_parse(m.group(1)), MentionKind.USER)

    return _regex_matcher(pat, _t)


def _mk_channel_mention() -> _Matcher:
    pat = re.compile(r"<\#!?(\d+)>", _BASE)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        return MentionNode(Snowflake.try_parse(m.group(1)), MentionKind.CHANNEL)

    return _regex_matcher(pat, _t)


def _mk_role_mention() -> _Matcher:
    pat = re.compile(r"<@&(\d+)>", _BASE)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        return MentionNode(Snowflake.try_parse(m.group(1)), MentionKind.ROLE)

    return _regex_matcher(pat, _t)


# ---------------------------------------------------------------------------
# Matchers – emoji
# ---------------------------------------------------------------------------

# Standard emoji regex covering:
# - Country flag emoji (two regional indicator surrogate pairs)
# - Digit emoji (digit followed by enclosing mark / variation selector + combining enclosing keycap)
# - Surrogate pairs (astral plane characters in Python are single code points, matched by range)
# - Miscellaneous emoji characters
_STANDARD_EMOJI_PATTERN = re.compile(
    r"("
    # Country flag emoji (regional indicator symbols)
    r"[\U0001F1E6-\U0001F1FF]{2}|"
    # Digit emoji (e.g. 1️⃣ - digit + \uFE0F + \u20E3)
    r"\d\uFE0F?\u20E3|"
    # Surrogate-pair emoji in Python = astral code points
    r"[\U0001F000-\U0001FAFF]|"
    # Miscellaneous characters
    r"["
    r"\u2600-\u2604"
    r"\u260E\u2611"
    r"\u2614-\u2615"
    r"\u2618\u261D\u2620"
    r"\u2622-\u2623"
    r"\u2626\u262A"
    r"\u262E-\u262F"
    r"\u2638-\u263A"
    r"\u2640\u2642"
    r"\u2648-\u2653"
    r"\u265F-\u2660"
    r"\u2663"
    r"\u2665-\u2666"
    r"\u2668\u267B"
    r"\u267E-\u267F"
    r"\u2692-\u2697"
    r"\u2699"
    r"\u269B-\u269C"
    r"\u26A0-\u26A1"
    r"\u26A7"
    r"\u26AA-\u26AB"
    r"\u26B0-\u26B1"
    r"\u26BD-\u26BE"
    r"\u26C4-\u26C5"
    r"\u26C8"
    r"\u26CE-\u26CF"
    r"\u26D1"
    r"\u26D3-\u26D4"
    r"\u26E9-\u26EA"
    r"\u26F0-\u26F5"
    r"\u26F7-\u26FA"
    r"\u26FD"
    r"]"
    r")",
    _BASE,
)


def _mk_standard_emoji() -> _Matcher:
    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        return EmojiNode(id=None, name=m.group(1), is_animated=False)

    return _regex_matcher(_STANDARD_EMOJI_PATTERN, _t)


def _mk_coded_standard_emoji() -> _Matcher:
    pat = re.compile(r":([\w_]+):", _BASE)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode | None:
        code = m.group(1)
        # Look up the code in the emoji index (code -> emoji char)
        try:
            from discord_chat_exporter.core.discord.models.emoji_index import CODE_TO_EMOJI
        except ImportError:
            return None
        emoji_char = CODE_TO_EMOJI.get(code)
        if emoji_char is None:
            return None
        return EmojiNode(id=None, name=emoji_char, is_animated=False)

    return _regex_matcher(pat, _t)


def _mk_custom_emoji() -> _Matcher:
    pat = re.compile(r"<(a)?:(.+?):(\d+?)>", _BASE)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        is_animated = bool(m.group(1) and m.group(1).strip())
        name = m.group(2)
        eid = Snowflake.try_parse(m.group(3))
        return EmojiNode(id=eid, name=name, is_animated=is_animated)

    return _regex_matcher(pat, _t)


# ---------------------------------------------------------------------------
# Matchers – links
# ---------------------------------------------------------------------------


def _mk_auto_link() -> _Matcher:
    pat = re.compile(r"""(https?://\S*[^\.,:;\"'\s])""", _BASE)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        return LinkNode(m.group(1))

    return _regex_matcher(pat, _t)


def _mk_hidden_link() -> _Matcher:
    pat = re.compile(r"""<(https?://\S*[^\.,:;\"'\s])>""", _BASE)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        return LinkNode(m.group(1))

    return _regex_matcher(pat, _t)


def _mk_masked_link() -> _Matcher:
    pat = re.compile(r"\[(.+?)\]\((.+?)\)", _BASE)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        url = m.group(2)
        children = _parse(d, _seg_from_group(s, m, 1), _NODE_MATCHER)
        return LinkNode(url, children)

    return _regex_matcher(pat, _t)


# ---------------------------------------------------------------------------
# Matchers – text escapes
# ---------------------------------------------------------------------------


def _mk_shrug_text() -> _Matcher:
    return _string_matcher(
        r"¯\_(ツ)_/¯",
        lambda s: TextNode(str(s)),
    )


def _mk_ignored_emoji_text() -> _Matcher:
    pat = re.compile(r"([\u26A7\u2640\u2642\u2695\u267E\u00A9\u00AE\u2122])", _BASE)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        return TextNode(m.group(1))

    return _regex_matcher(pat, _t)


def _mk_escaped_symbol_text() -> _Matcher:
    # In Python, \p{So} is not supported, but we can approximate with the
    # Unicode category "Symbol, Other". We match backslash followed by
    # a character outside ASCII letters/digits/whitespace that is a symbol or
    # an astral-plane character.
    pat = re.compile(
        r"\\("
        r"[\U00010000-\U0010FFFF]"  # astral characters (surrogate pairs in C#)
        r"|[\u2000-\u2BFF\u2E00-\u2E7F\u3000-\u303F\uFE00-\uFE0F]"  # common symbol ranges
        r"|[\u00A0-\u00FF]"  # latin-1 symbols
        r")",
        _BASE,
    )

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        return TextNode(m.group(1))

    return _regex_matcher(pat, _t)


def _mk_escaped_character_text() -> _Matcher:
    pat = re.compile(r"\\([^a-zA-Z0-9\s])", _BASE)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        return TextNode(m.group(1))

    return _regex_matcher(pat, _t)


# ---------------------------------------------------------------------------
# Matchers – misc
# ---------------------------------------------------------------------------


def _mk_timestamp() -> _Matcher:
    pat = re.compile(r"<t:(-?\d+)(?::(\w))?>", _BASE)

    def _t(d: int, s: _Segment, m: re.Match[str]) -> MarkdownNode:
        try:
            epoch_seconds = int(m.group(1))
            instant = datetime.fromtimestamp(epoch_seconds, tz=timezone.utc)

            raw_format = m.group(2) if m.group(2) else None
            if raw_format:
                raw_format = raw_format.strip()
                if not raw_format:
                    raw_format = None

            if raw_format is not None:
                if raw_format in ("t", "T", "d", "D", "f", "F"):
                    fmt: str | None = raw_format
                elif raw_format in ("r", "R"):
                    # Relative format: ignore because it doesn't make sense in static export
                    fmt = None
                else:
                    # Unknown format => invalid timestamp
                    return TIMESTAMP_INVALID
            else:
                fmt = None

            return TimestampNode(instant, fmt)
        except (ValueError, OverflowError, OSError):
            return TIMESTAMP_INVALID

    return _regex_matcher(pat, _t)


# ---------------------------------------------------------------------------
# Build the aggregate matchers
# ---------------------------------------------------------------------------

# We need forward references because some matchers reference the top-level
# node matcher (for recursive parsing). We solve this by creating the
# individual matchers lazily and building the aggregate at module init.

_BOLD_MATCHER = _mk_bold()
_UNDERLINE_MATCHER = _mk_underline()

# Full node matcher (all matchers in priority order)
_NODE_MATCHER = _aggregate_matcher(
    [
        # Escaped text
        _mk_shrug_text(),
        _mk_ignored_emoji_text(),
        _mk_escaped_symbol_text(),
        _mk_escaped_character_text(),
        # Formatting (most specific first)
        _mk_italic_bold(),
        _mk_italic_underline(),
        _mk_bold(),
        _mk_italic(),
        _mk_underline(),
        _mk_italic_alt(),
        _mk_strikethrough(),
        _mk_spoiler(),
        _mk_multi_line_quote(),
        _mk_repeated_single_line_quote(),
        _mk_single_line_quote(),
        _mk_heading(),
        _mk_list(),
        # Code blocks
        _mk_multi_line_code_block(),
        _mk_inline_code_block(),
        # Mentions
        _mk_everyone_mention(),
        _mk_here_mention(),
        _mk_user_mention(),
        _mk_channel_mention(),
        _mk_role_mention(),
        # Links
        _mk_masked_link(),
        _mk_auto_link(),
        _mk_hidden_link(),
        # Emoji
        _mk_standard_emoji(),
        _mk_custom_emoji(),
        _mk_coded_standard_emoji(),
        # Misc
        _mk_timestamp(),
    ]
)

# Minimal matcher (for plain-text / non-multimedia formats)
_MINIMAL_NODE_MATCHER = _aggregate_matcher(
    [
        # Mentions
        _mk_everyone_mention(),
        _mk_here_mention(),
        _mk_user_mention(),
        _mk_channel_mention(),
        _mk_role_mention(),
        # Emoji
        _mk_custom_emoji(),
        # Misc
        _mk_timestamp(),
    ]
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse(markdown: str) -> list[MarkdownNode]:
    """Parse Discord markdown text into an AST (full formatting)."""
    segment = _Segment(markdown, 0, len(markdown))
    return _parse(0, segment, _NODE_MATCHER)


def parse_minimal(markdown: str) -> list[MarkdownNode]:
    """Parse Discord markdown text into an AST (minimal - mentions, emoji, timestamps only)."""
    segment = _Segment(markdown, 0, len(markdown))
    return _parse(0, segment, _MINIMAL_NODE_MATCHER)


def _extract_nodes_of_type(
    nodes: Sequence[MarkdownNode],
    node_type: type,
    result: list[MarkdownNode],
) -> None:
    """Recursively extract all nodes of a given type from the AST."""
    for node in nodes:
        if isinstance(node, node_type):
            result.append(node)
        children = get_children(node)
        if children is not None:
            _extract_nodes_of_type(children, node_type, result)
        # Also check ListNode items
        if isinstance(node, ListNode):
            _extract_nodes_of_type(list(node.items), node_type, result)


def extract_emojis(markdown: str) -> list[EmojiNode]:
    """Extract all emoji nodes from parsed markdown."""
    nodes = parse(markdown)
    result: list[MarkdownNode] = []
    _extract_nodes_of_type(nodes, EmojiNode, result)
    return result  # type: ignore[return-value]


def extract_links(markdown: str) -> list[LinkNode]:
    """Extract all link nodes from parsed markdown."""
    nodes = parse(markdown)
    result: list[MarkdownNode] = []
    _extract_nodes_of_type(nodes, LinkNode, result)
    return result  # type: ignore[return-value]
