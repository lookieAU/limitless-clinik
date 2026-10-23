import re

from agent.pipeline.state import TurnState
from agent.repo import verified

STATUS_PATTERNS = (
    re.compile(r"\b(confirmed|booked|scheduled|all set|set for|is set|cancell?ed|reserved|locked in)\b", re.IGNORECASE),
    re.compile(r"(कन्फर्म|बुक|पक्का|रद्द|रख दिया)"),
    re.compile(r"\b(confirm|book|cancel)\s*(ho|kar)\s*(gaya|gayi|gya|diya|di|dia)\b", re.IGNORECASE),
)


CLOCK = re.compile(r"\b(\d{1,2}):(\d{2})\b")
REF = re.compile(r"\b[A-Z]{2}-\d{4}\b", re.IGNORECASE)
DOCTOR = re.compile(r"\bDr\.? [A-Z][a-z]+(?: [A-Z][a-z]+)?")
ASKS_AGAIN = re.compile(r"\?|say yes|let me know if|हाँ कहें|बताइए", re.IGNORECASE)


def anchors(text: str) -> set[str]:
    clocks = {f"{int(hour)}:{minute}" for hour, minute in CLOCK.findall(text)}
    return clocks | {ref.upper() for ref in REF.findall(text)}


def repeats_system_lines(prose: str, system_text: str) -> bool:
    if anchors(prose) & anchors(system_text):
        return True
    if any(name.lower() in prose.lower() for name in DOCTOR.findall(system_text)):
        return True
    return "?" in system_text and bool(ASKS_AGAIN.search(prose))


def prose_violations(prose: str) -> list[str]:
    return [match.group(0) for pattern in STATUS_PATTERNS for match in pattern.finditer(prose)]


def stale_bookings(state: TurnState) -> list[str]:
    ttl = state.ctx.settings.freshness_ttl_s
    now = state.ctx.clock.now()
    stale = []
    for booking_id in dict.fromkeys(state.booking_ids()):
        row = verified.get(state.conn, booking_id)
        if row is None or not verified.is_fresh(row, now, ttl, state.session_id):
            stale.append(booking_id)
    return stale
