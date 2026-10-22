from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from shared.clock import FixedClock, OffsetClock
from shared.time import format_dual, local_to_utc, parse_utc, to_iso_z, week_start

IST = ZoneInfo("Asia/Kolkata")
SGT = ZoneInfo("Asia/Singapore")
DEMO_NOW = parse_utc("2026-11-02T03:30:00Z")


def test_naive_datetimes_are_rejected():
    with pytest.raises(ValueError):
        FixedClock(datetime(2026, 11, 2, 9, 0))


def test_iso_round_trip_uses_z_suffix():
    assert to_iso_z(DEMO_NOW) == "2026-11-02T03:30:00Z"
    assert parse_utc("2026-11-02T09:00:00+05:30") == DEMO_NOW


def test_clinic_wall_time_resolves_to_utc():
    assert local_to_utc(date(2026, 11, 5), time(15, 0), IST) == datetime(2026, 11, 5, 9, 30, tzinfo=UTC)


def test_week_starts_monday():
    assert week_start(date(2026, 11, 5)) == date(2026, 11, 2)


def test_dual_display_when_timezones_differ():
    slot = datetime(2026, 11, 5, 9, 30, tzinfo=UTC)
    assert format_dual(slot, IST, SGT) == "Thu 5 Nov, 3:00 pm IST (5:30 pm SGT)"
    assert format_dual(slot, IST, IST) == "Thu 5 Nov, 3:00 pm IST"


def test_fixed_clock_advances():
    clock = FixedClock(DEMO_NOW)
    clock.advance(timedelta(days=1))
    assert clock.now() == DEMO_NOW + timedelta(days=1)


def test_offset_clock_tracks_base_and_jumps():
    base = FixedClock(datetime(2030, 1, 1, tzinfo=UTC))
    clock = OffsetClock(DEMO_NOW, base=base)
    base.advance(timedelta(seconds=90))
    clock.advance(timedelta(days=1))
    assert clock.now() == DEMO_NOW + timedelta(days=1, seconds=90)
