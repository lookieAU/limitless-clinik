from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TZ_ABBREVIATIONS = {
    "Asia/Kolkata": "IST",
    "Asia/Singapore": "SGT",
    "Asia/Dubai": "GST",
    "UTC": "UTC",
}


def ensure_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        raise ValueError("naive datetime is not allowed")
    return moment.astimezone(UTC)


def parse_utc(text: str) -> datetime:
    return ensure_utc(datetime.fromisoformat(text))


def to_iso_z(moment: datetime) -> str:
    return ensure_utc(moment).isoformat(timespec="seconds").replace("+00:00", "Z")


def local_to_utc(day: date, wall: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, wall, tzinfo=tz).astimezone(UTC)


def to_local(moment: datetime, tz: ZoneInfo) -> datetime:
    return ensure_utc(moment).astimezone(tz)


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def tz_label(tz: ZoneInfo) -> str:
    return TZ_ABBREVIATIONS.get(tz.key, tz.key)


def format_clock(moment: datetime) -> str:
    hour = moment.hour % 12 or 12
    suffix = "am" if moment.hour < 12 else "pm"
    return f"{hour}:{moment.minute:02d} {suffix}"


def format_day(moment: datetime) -> str:
    return f"{moment:%a} {moment.day} {moment:%b}"


def format_dual(moment: datetime, clinic_tz: ZoneInfo, customer_tz: ZoneInfo) -> str:
    clinic_local = to_local(moment, clinic_tz)
    text = f"{format_day(clinic_local)}, {format_clock(clinic_local)} {tz_label(clinic_tz)}"
    if customer_tz.key == clinic_tz.key:
        return text
    customer_local = to_local(moment, customer_tz)
    other = format_clock(customer_local)
    if customer_local.date() != clinic_local.date():
        other = f"{format_day(customer_local)}, {other}"
    return f"{text} ({other} {tz_label(customer_tz)})"
