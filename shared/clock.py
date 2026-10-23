import os
from datetime import UTC, datetime, timedelta
from typing import Protocol

from shared.time import ensure_utc, parse_utc


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    def __init__(self, at: datetime):
        self._at = ensure_utc(at)

    def now(self) -> datetime:
        return self._at

    def advance(self, delta: timedelta) -> None:
        self._at += delta


class OffsetClock:
    def __init__(self, start: datetime, base: Clock | None = None):
        self._base = base or SystemClock()
        self._offset = ensure_utc(start) - self._base.now()

    def now(self) -> datetime:
        return self._base.now() + self._offset

    def advance(self, delta: timedelta) -> None:
        self._offset += delta


def clock_from_env() -> Clock:
    demo_now = os.environ.get("DEMO_NOW", "").strip()
    return OffsetClock(parse_utc(demo_now) if demo_now else SystemClock().now())
