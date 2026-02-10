"""Hand-rolled recursive-descent parser for the message filter DSL.

Grammar (informal)::

    filter       = chained EOF
    chained      = unary ( operator unary )*
    operator     = '|' | '&' | <whitespace>     (whitespace = implicit AND)
    unary        = negation | grouped | primitive
    negation     = ('-' | '~') (grouped | primitive)
    grouped      = '(' chained ')'
    primitive     = prefixed | contains
    prefixed     = from_filter | mentions_filter | reaction_filter | has_filter
    from_filter  = 'from:' string
    mentions_filter = 'mentions:' string
    reaction_filter = 'reaction:' string
    has_filter   = 'has:' has_kind
    has_kind     = 'link' | 'embed' | 'file' | 'video' | 'image' | 'sound'
                   | 'pin' | 'invite'
    contains     = string
    string       = quoted_string | unquoted_string
    quoted_string = ('"' | "'") escaped_chars close_quote
    unquoted_string = <chars not in  ()\"'-~|& and not whitespace>+

Operators bind left-to-right.  ``|`` and ``&`` are explicit operators;
adjacent terms separated only by whitespace are joined with implicit AND.
"""

from __future__ import annotations

from discord_chat_exporter.core.exporting.filtering.base import MessageFilter
from discord_chat_exporter.core.exporting.filtering.combinators import (
    BinaryExpressionKind,
    BinaryExpressionMessageFilter,
    NegatedMessageFilter,
)
from discord_chat_exporter.core.exporting.filtering.filters import (
    ContainsMessageFilter,
    FromMessageFilter,
    HasMessageFilter,
    MentionsMessageFilter,
    ReactionMessageFilter,
)

# Characters that are reserved tokens in the grammar and therefore cannot
# appear inside an unquoted string value.
_SPECIAL_CHARS = frozenset(" ()'\"\\-~|&")


class FilterParseError(Exception):
    """Raised when the filter DSL text cannot be parsed."""


class _Parser:
    """Stateful recursive-descent parser."""

    def __init__(self, text: str) -> None:
        self._text = text
        self._pos = 0

    # -- helpers -----------------------------------------------------------

    @property
    def _at_end(self) -> bool:
        return self._pos >= len(self._text)

    def _peek(self) -> str:
        if self._at_end:
            return ""
        return self._text[self._pos]

    def _advance(self) -> str:
        ch = self._text[self._pos]
        self._pos += 1
        return ch

    def _skip_whitespace(self) -> int:
        """Skip whitespace and return the number of characters skipped."""
        start = self._pos
        while not self._at_end and self._text[self._pos] == " ":
            self._pos += 1
        return self._pos - start

    def _expect(self, ch: str) -> None:
        if self._at_end or self._text[self._pos] != ch:
            raise FilterParseError(
                f"Expected {ch!r} at position {self._pos}"
            )
        self._pos += 1

    def _match_string_ci(self, target: str) -> bool:
        """Try to match *target* (case-insensitive) at the current position.

        If successful the position is advanced past *target* and ``True`` is
        returned; otherwise the position is unchanged and ``False`` is
        returned.
        """
        end = self._pos + len(target)
        if end > len(self._text):
            return False
        if self._text[self._pos:end].lower() == target.lower():
            self._pos = end
            return True
        return False

    # -- string parsing ----------------------------------------------------

    def _parse_quoted_string(self) -> str:
        """Parse a single- or double-quoted string, handling backslash escapes."""
        quote = self._advance()  # consume opening quote
        parts: list[str] = []
        while not self._at_end:
            ch = self._peek()
            if ch == "\\":
                self._advance()  # skip backslash
                if self._at_end:
                    raise FilterParseError(
                        "Unexpected end of input after backslash"
                    )
                parts.append(self._advance())
            elif ch == quote:
                self._advance()  # consume closing quote
                return "".join(parts)
            else:
                parts.append(self._advance())
        raise FilterParseError("Unterminated quoted string")

    def _parse_unquoted_string(self) -> str:
        """Parse an unquoted string (stops at special characters or whitespace)."""
        parts: list[str] = []
        while not self._at_end:
            ch = self._peek()
            if ch == "\\":
                self._advance()  # skip backslash
                if self._at_end:
                    raise FilterParseError(
                        "Unexpected end of input after backslash"
                    )
                parts.append(self._advance())
            elif ch in _SPECIAL_CHARS:
                break
            else:
                parts.append(self._advance())
        if not parts:
            raise FilterParseError(
                f"Expected a text string at position {self._pos}"
            )
        return "".join(parts)

    def _parse_string(self) -> str:
        if not self._at_end and self._peek() in ("'", '"'):
            return self._parse_quoted_string()
        return self._parse_unquoted_string()

    # -- filter rules ------------------------------------------------------

    def _try_parse_prefixed(self) -> MessageFilter | None:
        """Try to parse ``from:``, ``mentions:``, ``reaction:``, or ``has:``."""
        saved = self._pos

        for prefix, factory in (
            ("from:", lambda v: FromMessageFilter(v)),
            ("mentions:", lambda v: MentionsMessageFilter(v)),
            ("reaction:", lambda v: ReactionMessageFilter(v)),
        ):
            if self._match_string_ci(prefix):
                try:
                    value = self._parse_string()
                except FilterParseError:
                    self._pos = saved
                    return None
                return factory(value)

        # has: needs special handling because the value is an enum keyword.
        if self._match_string_ci("has:"):
            try:
                value = self._parse_string()
            except FilterParseError:
                self._pos = saved
                return None
            try:
                return HasMessageFilter(value)
            except ValueError:
                self._pos = saved
                return None

        return None

    def _parse_primitive(self) -> MessageFilter:
        """Parse a prefixed filter or a bare ``contains`` filter."""
        result = self._try_parse_prefixed()
        if result is not None:
            return result
        # Fall through to a bare contains term.
        text = self._parse_string()
        return ContainsMessageFilter(text)

    def _parse_grouped(self) -> MessageFilter:
        """Parse ``'(' chained ')'``."""
        self._expect("(")
        self._skip_whitespace()
        result = self._parse_chained()
        self._skip_whitespace()
        self._expect(")")
        return result

    def _parse_unary(self) -> MessageFilter:
        """Parse a unary expression: negation, grouped, or primitive."""
        if not self._at_end and self._peek() in ("-", "~"):
            self._advance()  # consume negation operator
            if not self._at_end and self._peek() == "(":
                inner = self._parse_grouped()
            else:
                inner = self._parse_primitive()
            return NegatedMessageFilter(inner)

        if not self._at_end and self._peek() == "(":
            return self._parse_grouped()

        return self._parse_primitive()

    def _parse_chained(self) -> MessageFilter:
        """Parse a chain of unary expressions joined by ``|``, ``&``, or whitespace."""
        left = self._parse_unary()

        while True:
            saved = self._pos
            ws_count = self._skip_whitespace()

            if self._at_end:
                break

            ch = self._peek()

            # Explicit operator
            if ch == "|":
                self._advance()
                self._skip_whitespace()
                right = self._parse_unary()
                left = BinaryExpressionMessageFilter(
                    left, right, BinaryExpressionKind.OR
                )
            elif ch == "&":
                self._advance()
                self._skip_whitespace()
                right = self._parse_unary()
                left = BinaryExpressionMessageFilter(
                    left, right, BinaryExpressionKind.AND
                )
            elif ws_count > 0 and ch not in (")", ""):
                # Implicit AND: whitespace between two operands.
                try:
                    right = self._parse_unary()
                except FilterParseError:
                    # If the next token isn't a valid operand, stop chaining.
                    self._pos = saved
                    break
                left = BinaryExpressionMessageFilter(
                    left, right, BinaryExpressionKind.AND
                )
            else:
                # Nothing more to chain (e.g. closing paren).
                self._pos = saved
                break

        return left

    # -- entry point -------------------------------------------------------

    def parse(self) -> MessageFilter:
        self._skip_whitespace()
        result = self._parse_chained()
        self._skip_whitespace()
        if not self._at_end:
            raise FilterParseError(
                f"Unexpected character {self._peek()!r} at position {self._pos}"
            )
        return result


def parse_filter(text: str) -> MessageFilter:
    """Parse a filter DSL string and return the corresponding filter tree.

    Parameters
    ----------
    text:
        The filter expression, e.g. ``"from:user has:image"``.

    Returns
    -------
    MessageFilter
        A composite filter that can be evaluated against messages.

    Raises
    ------
    FilterParseError
        If *text* cannot be parsed.
    """
    if not text or not text.strip():
        raise FilterParseError("Filter expression is empty")
    return _Parser(text).parse()
