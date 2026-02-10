"""Tests for the Snowflake type."""

from datetime import datetime, timezone

import pytest

from discord_chat_exporter.core.discord.snowflake import Snowflake


class TestSnowflakeBasics:
    def test_value(self):
        s = Snowflake(123456789)
        assert s.value == 123456789

    def test_str(self):
        assert str(Snowflake(42)) == "42"

    def test_int(self):
        assert int(Snowflake(42)) == 42

    def test_repr(self):
        assert repr(Snowflake(42)) == "Snowflake(42)"

    def test_bool_nonzero(self):
        assert bool(Snowflake(1)) is True

    def test_bool_zero(self):
        assert bool(Snowflake(0)) is False

    def test_hash(self):
        a = Snowflake(100)
        b = Snowflake(100)
        assert hash(a) == hash(b)
        assert {a, b} == {a}

    def test_equality(self):
        assert Snowflake(100) == Snowflake(100)
        assert Snowflake(100) != Snowflake(200)

    def test_ordering(self):
        assert Snowflake(1) < Snowflake(2)
        assert Snowflake(2) > Snowflake(1)
        assert Snowflake(1) <= Snowflake(1)
        assert Snowflake(1) >= Snowflake(1)

    def test_zero_sentinel(self):
        assert Snowflake.ZERO == Snowflake(0)
        assert Snowflake.ZERO.value == 0


class TestSnowflakeTimestamp:
    def test_to_date(self):
        # Known Discord snowflake: 175928847299117063
        # Created at 2016-04-30T11:18:36.163Z
        s = Snowflake(175928847299117063)
        dt = s.to_date()
        assert dt.year == 2016
        assert dt.month == 4
        assert dt.day == 30
        assert dt.tzinfo == timezone.utc

    def test_from_date_roundtrip(self):
        dt = datetime(2020, 1, 1, tzinfo=timezone.utc)
        s = Snowflake.from_date(dt)
        recovered = s.to_date()
        # Sub-millisecond precision is lost, but date should be close
        assert abs((recovered - dt).total_seconds()) < 1


class TestSnowflakeParsing:
    def test_parse_int_string(self):
        s = Snowflake.parse("175928847299117063")
        assert s.value == 175928847299117063

    def test_parse_iso_date(self):
        s = Snowflake.parse("2020-01-01T00:00:00+00:00")
        assert s.to_date().year == 2020

    def test_parse_invalid_raises(self):
        with pytest.raises(ValueError, match="Invalid snowflake"):
            Snowflake.parse("not-a-snowflake")

    def test_try_parse_none(self):
        assert Snowflake.try_parse(None) is None

    def test_try_parse_empty(self):
        assert Snowflake.try_parse("") is None
        assert Snowflake.try_parse("  ") is None

    def test_try_parse_invalid(self):
        assert Snowflake.try_parse("xyz") is None


class TestSnowflakePydantic:
    def test_pydantic_model_with_snowflake(self):
        from pydantic import BaseModel

        class TestModel(BaseModel):
            model_config = {"frozen": True}
            id: Snowflake

        m = TestModel(id=Snowflake(42))
        assert m.id == Snowflake(42)

    def test_pydantic_from_int(self):
        from pydantic import BaseModel

        class TestModel(BaseModel):
            id: Snowflake

        m = TestModel(id=42)
        assert m.id == Snowflake(42)

    def test_pydantic_from_string(self):
        from pydantic import BaseModel

        class TestModel(BaseModel):
            id: Snowflake

        m = TestModel(id="12345")
        assert m.id == Snowflake(12345)

    def test_pydantic_serialization(self):
        from pydantic import BaseModel

        class TestModel(BaseModel):
            id: Snowflake

        m = TestModel(id=Snowflake(42))
        data = m.model_dump()
        assert data["id"] == 42
