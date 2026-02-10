"""Discord Snowflake type - wraps a 64-bit integer with timestamp extraction."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import total_ordering
from typing import Any

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema

# Discord epoch: 2015-01-01T00:00:00Z in milliseconds
_DISCORD_EPOCH_MS = 1420070400000


@total_ordering
class Snowflake:
    """Immutable, hashable Discord snowflake ID."""

    __slots__ = ("_value",)

    def __init__(self, value: int) -> None:
        self._value = value

    @property
    def value(self) -> int:
        return self._value

    def to_date(self) -> datetime:
        """Extract the creation timestamp from this snowflake."""
        ms = (self._value >> 22) + _DISCORD_EPOCH_MS
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)

    @classmethod
    def from_date(cls, dt: datetime) -> Snowflake:
        """Create a snowflake from a datetime (for range queries)."""
        ms = int(dt.timestamp() * 1000) - _DISCORD_EPOCH_MS
        return cls(ms << 22)

    @classmethod
    def try_parse(cls, value: str | None) -> Snowflake | None:
        """Try to parse a string as a snowflake (number or ISO date)."""
        if not value or not value.strip():
            return None

        # Try as integer
        try:
            return cls(int(value))
        except ValueError:
            pass

        # Try as ISO date
        try:
            dt = datetime.fromisoformat(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return cls.from_date(dt)
        except ValueError:
            pass

        return None

    @classmethod
    def parse(cls, value: str) -> Snowflake:
        """Parse a string as a snowflake, raising on failure."""
        result = cls.try_parse(value)
        if result is None:
            raise ValueError(f"Invalid snowflake: {value!r}")
        return result

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Snowflake):
            return self._value == other._value
        return NotImplemented

    def __lt__(self, other: object) -> bool:
        if isinstance(other, Snowflake):
            return self._value < other._value
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._value)

    def __repr__(self) -> str:
        return f"Snowflake({self._value})"

    def __str__(self) -> str:
        return str(self._value)

    def __int__(self) -> int:
        return self._value

    def __bool__(self) -> bool:
        return self._value != 0

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls._pydantic_validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda v: v._value, info_arg=False
            ),
        )

    @classmethod
    def _pydantic_validate(cls, value: Any) -> Snowflake:
        if isinstance(value, Snowflake):
            return value
        if isinstance(value, int):
            return cls(value)
        if isinstance(value, str):
            return cls(int(value))
        raise ValueError(f"Cannot convert {type(value)} to Snowflake")

    ZERO: Snowflake


Snowflake.ZERO = Snowflake(0)
