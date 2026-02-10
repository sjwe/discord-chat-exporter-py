"""Tests for the Discord markdown parser."""

from discord_chat_exporter.core.markdown.nodes import (
    EmojiNode,
    FormattingKind,
    FormattingNode,
    HeadingNode,
    InlineCodeBlockNode,
    LinkNode,
    ListNode,
    MentionKind,
    MentionNode,
    MultiLineCodeBlockNode,
    TextNode,
    TimestampNode,
)
from discord_chat_exporter.core.markdown.parser import (
    extract_emojis,
    extract_links,
    parse,
    parse_minimal,
)


def _text(nodes, idx=0):
    """Extract text from a TextNode at the given index."""
    return nodes[idx].text


class TestPlainText:
    def test_simple_text(self):
        nodes = parse("hello world")
        assert len(nodes) == 1
        assert isinstance(nodes[0], TextNode)
        assert nodes[0].text == "hello world"

    def test_empty_string(self):
        nodes = parse("")
        assert nodes == []


class TestFormatting:
    def test_bold(self):
        nodes = parse("**bold**")
        assert len(nodes) == 1
        assert isinstance(nodes[0], FormattingNode)
        assert nodes[0].kind == FormattingKind.BOLD
        assert _text(nodes[0].children) == "bold"

    def test_italic_asterisk(self):
        nodes = parse("*italic*")
        assert len(nodes) == 1
        assert isinstance(nodes[0], FormattingNode)
        assert nodes[0].kind == FormattingKind.ITALIC

    def test_italic_underscore(self):
        nodes = parse("_italic_")
        assert len(nodes) == 1
        assert isinstance(nodes[0], FormattingNode)
        assert nodes[0].kind == FormattingKind.ITALIC

    def test_underline(self):
        nodes = parse("__underline__")
        assert len(nodes) == 1
        assert isinstance(nodes[0], FormattingNode)
        assert nodes[0].kind == FormattingKind.UNDERLINE

    def test_strikethrough(self):
        nodes = parse("~~strikethrough~~")
        assert len(nodes) == 1
        assert isinstance(nodes[0], FormattingNode)
        assert nodes[0].kind == FormattingKind.STRIKETHROUGH

    def test_spoiler(self):
        nodes = parse("||spoiler||")
        assert len(nodes) == 1
        assert isinstance(nodes[0], FormattingNode)
        assert nodes[0].kind == FormattingKind.SPOILER

    def test_bold_italic(self):
        nodes = parse("***bold italic***")
        assert len(nodes) == 1
        # Should be bold wrapping italic, or italic wrapping bold
        assert isinstance(nodes[0], FormattingNode)

    def test_mixed_formatting_with_text(self):
        nodes = parse("hello **bold** world")
        assert len(nodes) == 3
        assert isinstance(nodes[0], TextNode)
        assert isinstance(nodes[1], FormattingNode)
        assert isinstance(nodes[2], TextNode)


class TestCodeBlocks:
    def test_inline_code(self):
        nodes = parse("`code`")
        assert len(nodes) == 1
        assert isinstance(nodes[0], InlineCodeBlockNode)
        assert nodes[0].code == "code"

    def test_multi_line_code_block(self):
        nodes = parse("```python\nprint('hello')\n```")
        assert len(nodes) == 1
        assert isinstance(nodes[0], MultiLineCodeBlockNode)
        assert nodes[0].language == "python"
        assert "print" in nodes[0].code

    def test_multi_line_code_block_no_language(self):
        nodes = parse("```\nsome code\n```")
        assert len(nodes) == 1
        assert isinstance(nodes[0], MultiLineCodeBlockNode)
        assert nodes[0].language == ""


class TestMentions:
    def test_user_mention(self):
        nodes = parse("<@123456789>")
        assert len(nodes) == 1
        assert isinstance(nodes[0], MentionNode)
        assert nodes[0].kind == MentionKind.USER
        assert nodes[0].target_id.value == 123456789

    def test_user_mention_with_exclamation(self):
        nodes = parse("<@!123456789>")
        assert len(nodes) == 1
        assert isinstance(nodes[0], MentionNode)
        assert nodes[0].kind == MentionKind.USER

    def test_channel_mention(self):
        nodes = parse("<#987654321>")
        assert len(nodes) == 1
        assert isinstance(nodes[0], MentionNode)
        assert nodes[0].kind == MentionKind.CHANNEL

    def test_role_mention(self):
        nodes = parse("<@&111222333>")
        assert len(nodes) == 1
        assert isinstance(nodes[0], MentionNode)
        assert nodes[0].kind == MentionKind.ROLE

    def test_everyone_mention(self):
        nodes = parse("@everyone")
        assert any(
            isinstance(n, MentionNode) and n.kind == MentionKind.EVERYONE
            for n in nodes
        )

    def test_here_mention(self):
        nodes = parse("@here")
        assert any(
            isinstance(n, MentionNode) and n.kind == MentionKind.HERE
            for n in nodes
        )


class TestEmoji:
    def test_custom_emoji(self):
        nodes = parse("<:LUL:123456789>")
        assert len(nodes) == 1
        assert isinstance(nodes[0], EmojiNode)
        assert nodes[0].name == "LUL"
        assert nodes[0].id.value == 123456789
        assert not nodes[0].is_animated

    def test_animated_emoji(self):
        nodes = parse("<a:dance:123456789>")
        assert len(nodes) == 1
        assert isinstance(nodes[0], EmojiNode)
        assert nodes[0].is_animated

    def test_extract_emojis(self):
        emojis = extract_emojis("hello <:LUL:123> world <:KEK:456>")
        assert len(emojis) == 2
        assert emojis[0].name == "LUL"
        assert emojis[1].name == "KEK"


class TestLinks:
    def test_auto_link(self):
        nodes = parse("https://example.com")
        assert any(isinstance(n, LinkNode) for n in nodes)
        link = next(n for n in nodes if isinstance(n, LinkNode))
        assert link.url == "https://example.com"

    def test_masked_link(self):
        nodes = parse("[click here](https://example.com)")
        assert any(isinstance(n, LinkNode) for n in nodes)
        link = next(n for n in nodes if isinstance(n, LinkNode))
        assert link.url == "https://example.com"

    def test_extract_links(self):
        links = extract_links("visit https://a.com and https://b.com")
        assert len(links) == 2
        urls = {l.url for l in links}
        assert "https://a.com" in urls
        assert "https://b.com" in urls


class TestHeadings:
    def test_heading_h1(self):
        # Heading regex requires ^ anchor and trailing newline
        nodes = parse("# Heading\n")
        assert any(isinstance(n, HeadingNode) for n in nodes)
        heading = next(n for n in nodes if isinstance(n, HeadingNode))
        assert heading.level == 1

    def test_heading_h3(self):
        nodes = parse("### Heading 3\n")
        assert any(isinstance(n, HeadingNode) for n in nodes)
        heading = next(n for n in nodes if isinstance(n, HeadingNode))
        assert heading.level == 3


class TestQuotes:
    def test_single_line_quote(self):
        nodes = parse("> quoted text")
        assert len(nodes) >= 1
        assert isinstance(nodes[0], FormattingNode)
        assert nodes[0].kind == FormattingKind.QUOTE


class TestLists:
    def test_unordered_list(self):
        text = "- item one\n- item two\n- item three"
        nodes = parse(text)
        assert any(isinstance(n, ListNode) for n in nodes)
        list_node = next(n for n in nodes if isinstance(n, ListNode))
        assert len(list_node.items) == 3


class TestTimestamps:
    def test_timestamp(self):
        nodes = parse("<t:1234567890>")
        assert any(isinstance(n, TimestampNode) for n in nodes)

    def test_timestamp_with_format(self):
        # "R" (relative) is intentionally stored as None since it doesn't
        # make sense in a static export; test with "f" (full date) instead
        nodes = parse("<t:1234567890:f>")
        assert any(isinstance(n, TimestampNode) for n in nodes)
        ts = next(n for n in nodes if isinstance(n, TimestampNode))
        assert ts.format == "f"

    def test_timestamp_relative_format_is_none(self):
        nodes = parse("<t:1234567890:R>")
        ts = next(n for n in nodes if isinstance(n, TimestampNode))
        assert ts.format is None


class TestSpecialCases:
    def test_shrug_kaomoji(self):
        # Should not be consumed as an escape sequence
        nodes = parse(r"¯\_(ツ)_/¯")
        text = "".join(n.text for n in nodes if isinstance(n, TextNode))
        assert "¯" in text
        assert "ツ" in text

    def test_parse_minimal_only_mentions(self):
        nodes = parse_minimal("hello **bold** <@123>")
        # Should have text and mention, but NOT formatted bold
        has_mention = any(isinstance(n, MentionNode) for n in nodes)
        has_formatting = any(isinstance(n, FormattingNode) for n in nodes)
        assert has_mention
        assert not has_formatting
