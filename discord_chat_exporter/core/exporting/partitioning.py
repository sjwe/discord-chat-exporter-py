"""Partition limit for splitting exports into multiple files."""

from __future__ import annotations

import re


class PartitionLimit:
    """Base class for partition limits."""

    def is_reached(self, messages_written: int, bytes_written: int) -> bool:
        raise NotImplementedError

    @staticmethod
    def null() -> PartitionLimit:
        return _NullPartitionLimit()

    @classmethod
    def try_parse(cls, value: str) -> PartitionLimit | None:
        # Try file size (e.g. "10mb", "1.5gb", "500kb")
        m = re.match(r"^\s*(\d+[.,]?\d*)\s*(\w)?b\s*$", value, re.IGNORECASE)
        if m:
            number = float(m.group(1).replace(",", "."))
            mag_char = (m.group(2) or "").upper()
            magnitude = {"G": 1_000_000_000, "M": 1_000_000, "K": 1_000, "": 1}.get(mag_char)
            if magnitude is not None:
                return _FileSizePartitionLimit(int(number * magnitude))

        # Try message count
        try:
            count = int(value.strip())
            return _MessageCountPartitionLimit(count)
        except ValueError:
            pass

        return None

    @classmethod
    def parse(cls, value: str) -> PartitionLimit:
        result = cls.try_parse(value)
        if result is None:
            raise ValueError(f"Invalid partition limit: {value!r}")
        return result


class _NullPartitionLimit(PartitionLimit):
    def is_reached(self, messages_written: int, bytes_written: int) -> bool:
        return False


class _FileSizePartitionLimit(PartitionLimit):
    def __init__(self, limit_bytes: int) -> None:
        self._limit = limit_bytes

    def is_reached(self, messages_written: int, bytes_written: int) -> bool:
        return bytes_written >= self._limit


class _MessageCountPartitionLimit(PartitionLimit):
    def __init__(self, limit: int) -> None:
        self._limit = limit

    def is_reached(self, messages_written: int, bytes_written: int) -> bool:
        return messages_written >= self._limit
