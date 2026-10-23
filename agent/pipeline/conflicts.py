from dataclasses import dataclass, field
from datetime import date, time, timedelta

from agent.vocab import WEEKDAYS
from shared.time import week_start

DATE_SUBJECTS = ("week", "date", "day")
SINGLE_VALUED = ("day", "date", "time_window", "week", "doctor", "clinic")
HORIZON_DAYS = 21


@dataclass(frozen=True)
class ClaimView:
    id: str
    subject: str
    value: str
    polarity: str
    seq: int


@dataclass
class Option:
    key: str
    keep: list[str]
    drop: list[str]
    day: date | None = None
    claim: ClaimView | None = None


@dataclass
class Conflict:
    kind: str
    options: list[Option]
    older: ClaimView
    newer: ClaimView


@dataclass
class Outcome:
    superseded: list[tuple[str, str]] = field(default_factory=list)
    conflict: Conflict | None = None


def view(row: dict) -> ClaimView:
    return ClaimView(row["id"], row["subject"], row["value"], row["polarity"], row["seq"])


def horizon(today: date) -> list[date]:
    return [today + timedelta(days=offset) for offset in range(HORIZON_DAYS)]


def claim_dates(claim: ClaimView, today: date) -> set[date]:
    if claim.subject == "week":
        monday = week_start(today) + timedelta(days=7 if claim.value == "next_week" else 0)
        return {monday + timedelta(days=offset) for offset in range(7)}
    if claim.subject == "date":
        return {date.fromisoformat(claim.value)}
    if claim.subject == "day":
        return {day for day in horizon(today) if WEEKDAYS[day.weekday()] == claim.value}
    return set()


def candidate_dates(claims: list[ClaimView], today: date) -> list[date]:
    dates = set(horizon(today))
    restricted = False
    for claim in sorted((c for c in claims if c.subject in DATE_SUBJECTS), key=lambda c: c.seq):
        matching = claim_dates(claim, today)
        if claim.polarity == "positive":
            dates &= matching
            restricted = restricted or claim.subject in ("week", "date")
        else:
            dates -= matching
    has_day = any(c.subject == "day" and c.polarity == "positive" for c in claims)
    if has_day and not restricted and dates:
        return [min(dates)]
    return sorted(dates)


def exact_time(claims: list[ClaimView]) -> time | None:
    for claim in reversed(claims):
        if claim.subject == "time_window" and claim.polarity == "positive" and ":" in claim.value:
            if not claim.value.startswith(("before_", "after_")):
                return time.fromisoformat(claim.value)
    return None


def contradiction(older: ClaimView, newer: ClaimView) -> Conflict:
    options = [Option("newer", keep=[newer.id], drop=[older.id], claim=newer), Option("older", keep=[older.id], drop=[newer.id], claim=older)]
    return Conflict("contradiction", options, older, newer)


def supersedes(old: ClaimView, new: ClaimView) -> bool:
    if old.subject != new.subject or old.subject not in SINGLE_VALUED:
        return False
    if old.polarity == "positive":
        return new.polarity == "positive" or old.value == new.value
    return old.value == new.value and new.polarity == "negative"


REPLACES = {"date": ("day", "week", "date"), "day": ("date",), "week": ("date",)}


def replaces_date(old: ClaimView, new: ClaimView) -> bool:
    both_positive = old.polarity == "positive" and new.polarity == "positive"
    return both_positive and old.subject in REPLACES.get(new.subject, ())


def date_conflict(live: list[ClaimView], claim: ClaimView, today: date) -> Conflict | None:
    if claim.polarity != "positive" or claim.subject not in DATE_SUBJECTS:
        return None
    if not candidate_dates(live, today):
        others = [c for c in live if c.subject in DATE_SUBJECTS and c.id != claim.id]
        for culprit in reversed(others):
            if candidate_dates([c for c in live if c.id != culprit.id], today):
                return contradiction(culprit, claim)
        return contradiction(others[-1], claim) if others else None
    if claim.subject != "day":
        return None
    weeks = [c for c in live if c.subject == "week" and c.polarity == "positive" and c.seq < claim.seq]
    if not weeks:
        return None
    in_context = candidate_dates(live, today)
    standalone = candidate_dates([c for c in live if not (c.subject == "week" and c.polarity == "positive")], today)
    if standalone and standalone[0] not in in_context:
        options = [
            Option("with_week", keep=[weeks[-1].id, claim.id], drop=[], day=in_context[0]),
            Option("standalone", keep=[claim.id], drop=[week.id for week in weeks], day=standalone[0]),
        ]
        return Conflict("ambiguous", options, weeks[-1], claim)
    return None


def apply_claims(active: list[ClaimView], new: list[ClaimView], today: date, detect: bool = True) -> Outcome:
    outcome = Outcome()
    live = list(active)
    for claim in sorted(new, key=lambda c: c.seq):
        detecting = detect and outcome.conflict is None
        for old in list(live):
            if old.subject == claim.subject and old.polarity == "negative" and claim.polarity == "positive" and old.value == claim.value:
                if detecting:
                    outcome.conflict = contradiction(old, claim)
                    detecting = False
                continue
            if supersedes(old, claim) or replaces_date(old, claim):
                live.remove(old)
                outcome.superseded.append((old.id, claim.id))
        live.append(claim)
        if detecting and (conflict := date_conflict(live, claim, today)):
            outcome.conflict = conflict
    return outcome


def option_matches(option: Option, answer: list[ClaimView], today: date) -> bool:
    if option.claim is not None:
        return any(
            a.subject == option.claim.subject and a.value == option.claim.value and a.polarity == option.claim.polarity
            for a in answer
        )
    date_claims = [a for a in answer if a.subject in DATE_SUBJECTS]
    if not date_claims or option.day is None:
        return False
    for claim in date_claims:
        inside = option.day in claim_dates(claim, today)
        if inside != (claim.polarity == "positive"):
            return False
    return True
