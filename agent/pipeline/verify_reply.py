import re

from agent.pipeline.state import TurnState
from agent.repo import verified

STATUS_PATTERNS = (
    re.compile(r"\b(confirmed|booked|scheduled|all set|set for|is set|cancell?ed|reserved|locked in)\b", re.IGNORECASE),
    re.compile(r"(कन्फर्म|बुक|पक्का|रद्द|रख दिया)"),
    re.compile(r"\b(confirm|book|cancel)\s*(ho|kar)\s*(gaya|gayi|gya|diya|di|dia)\b", re.IGNORECASE),
)


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
