"""Tests for the PartitionLimit parser."""

import pytest

from discord_chat_exporter.core.exporting.partitioning import PartitionLimit


class TestPartitionLimitParsing:
    def test_parse_megabytes(self):
        limit = PartitionLimit.parse("10mb")
        assert limit.is_reached(0, 10_000_000)
        assert not limit.is_reached(0, 9_999_999)

    def test_parse_gigabytes(self):
        limit = PartitionLimit.parse("1gb")
        assert limit.is_reached(0, 1_000_000_000)
        assert not limit.is_reached(0, 999_999_999)

    def test_parse_kilobytes(self):
        limit = PartitionLimit.parse("500kb")
        assert limit.is_reached(0, 500_000)
        assert not limit.is_reached(0, 499_999)

    def test_parse_bytes(self):
        limit = PartitionLimit.parse("1024b")
        assert limit.is_reached(0, 1024)

    def test_parse_case_insensitive(self):
        limit = PartitionLimit.parse("10MB")
        assert limit.is_reached(0, 10_000_000)

    def test_parse_with_spaces(self):
        limit = PartitionLimit.parse("  10 mb  ")
        assert limit.is_reached(0, 10_000_000)

    def test_parse_decimal(self):
        limit = PartitionLimit.parse("1.5gb")
        assert limit.is_reached(0, 1_500_000_000)
        assert not limit.is_reached(0, 1_499_999_999)

    def test_parse_message_count(self):
        limit = PartitionLimit.parse("100")
        assert limit.is_reached(100, 0)
        assert not limit.is_reached(99, 0)

    def test_parse_invalid_returns_error(self):
        with pytest.raises(ValueError, match="Invalid partition limit"):
            PartitionLimit.parse("not-a-limit")

    def test_try_parse_invalid_returns_none(self):
        assert PartitionLimit.try_parse("not-a-limit") is None

    def test_null_never_reached(self):
        limit = PartitionLimit.null()
        assert not limit.is_reached(999_999, 999_999_999)
