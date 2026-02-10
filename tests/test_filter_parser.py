"""Tests for the message filter DSL parser."""

import pytest

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
from discord_chat_exporter.core.exporting.filtering.parser import (
    FilterParseError,
    parse_filter,
)


class TestPrimitives:
    def test_bare_text(self):
        f = parse_filter("hello")
        assert isinstance(f, ContainsMessageFilter)

    def test_from_filter(self):
        f = parse_filter("from:user123")
        assert isinstance(f, FromMessageFilter)

    def test_mentions_filter(self):
        f = parse_filter("mentions:user123")
        assert isinstance(f, MentionsMessageFilter)

    def test_reaction_filter(self):
        f = parse_filter("reaction:thumbsup")
        assert isinstance(f, ReactionMessageFilter)

    def test_has_link(self):
        f = parse_filter("has:link")
        assert isinstance(f, HasMessageFilter)

    def test_has_image(self):
        f = parse_filter("has:image")
        assert isinstance(f, HasMessageFilter)

    def test_has_embed(self):
        f = parse_filter("has:embed")
        assert isinstance(f, HasMessageFilter)

    def test_has_invalid_falls_back_to_contains(self):
        # Invalid has: kind causes parser to backtrack and treat as bare text
        f = parse_filter("has:invalid_type")
        assert isinstance(f, ContainsMessageFilter)

    def test_quoted_string(self):
        f = parse_filter('"hello world"')
        assert isinstance(f, ContainsMessageFilter)

    def test_single_quoted_string(self):
        f = parse_filter("'hello world'")
        assert isinstance(f, ContainsMessageFilter)

    def test_from_quoted(self):
        f = parse_filter('from:"user name"')
        assert isinstance(f, FromMessageFilter)


class TestCombinators:
    def test_implicit_and(self):
        f = parse_filter("from:alice has:image")
        assert isinstance(f, BinaryExpressionMessageFilter)
        assert f._kind is BinaryExpressionKind.AND
        assert isinstance(f._first, FromMessageFilter)
        assert isinstance(f._second, HasMessageFilter)

    def test_explicit_and(self):
        f = parse_filter("from:alice & has:image")
        assert isinstance(f, BinaryExpressionMessageFilter)
        assert f._kind is BinaryExpressionKind.AND

    def test_explicit_or(self):
        f = parse_filter("from:alice | from:bob")
        assert isinstance(f, BinaryExpressionMessageFilter)
        assert f._kind is BinaryExpressionKind.OR

    def test_negation_dash(self):
        f = parse_filter("-from:alice")
        assert isinstance(f, NegatedMessageFilter)
        assert isinstance(f._inner, FromMessageFilter)

    def test_negation_tilde(self):
        f = parse_filter("~has:image")
        assert isinstance(f, NegatedMessageFilter)
        assert isinstance(f._inner, HasMessageFilter)

    def test_grouped(self):
        f = parse_filter("(from:alice | from:bob) has:image")
        assert isinstance(f, BinaryExpressionMessageFilter)
        assert f._kind is BinaryExpressionKind.AND
        # Left is the OR group
        assert isinstance(f._first, BinaryExpressionMessageFilter)
        assert f._first._kind is BinaryExpressionKind.OR
        # Right is has:image
        assert isinstance(f._second, HasMessageFilter)

    def test_negated_group(self):
        f = parse_filter("-(from:alice | from:bob)")
        assert isinstance(f, NegatedMessageFilter)
        assert isinstance(f._inner, BinaryExpressionMessageFilter)
        assert f._inner._kind is BinaryExpressionKind.OR

    def test_three_terms_implicit_and(self):
        f = parse_filter("from:alice has:image hello")
        # Left-to-right: (from:alice AND has:image) AND hello
        assert isinstance(f, BinaryExpressionMessageFilter)
        assert f._kind is BinaryExpressionKind.AND
        assert isinstance(f._first, BinaryExpressionMessageFilter)
        assert isinstance(f._second, ContainsMessageFilter)


class TestEdgeCases:
    def test_empty_raises(self):
        with pytest.raises(FilterParseError):
            parse_filter("")

    def test_whitespace_only_raises(self):
        with pytest.raises(FilterParseError):
            parse_filter("   ")

    def test_leading_trailing_whitespace(self):
        f = parse_filter("  from:alice  ")
        assert isinstance(f, FromMessageFilter)

    def test_case_insensitive_prefix(self):
        f = parse_filter("FROM:alice")
        assert isinstance(f, FromMessageFilter)

    def test_escaped_quote_in_string(self):
        f = parse_filter(r'"hello \"world\""')
        assert isinstance(f, ContainsMessageFilter)

    def test_unterminated_quote_raises(self):
        with pytest.raises(FilterParseError, match="Unterminated"):
            parse_filter('"hello')
