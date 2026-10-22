from agent.pipeline.compose import when
from agent.pipeline.conflicts import claim_dates, view
from agent.pipeline.consent import clinic_today
from agent.pipeline.state import TurnState
from agent.pipeline.templates import text
from agent.repo import sessions, verified
from shared.time import parse_utc, to_local

NEEDS_TARGET = ("reschedule", "cancel")


def narrow(state: TurnState, candidates: list[dict]) -> list[dict]:
    doctors = {c["value"] for c in state.new_claims if c["subject"] == "doctor" and c["polarity"] == "positive"}
    dated = [view(c) for c in state.new_claims if c["subject"] in ("day", "date") and c["polarity"] == "positive"]
    result = []
    for row in candidates:
        tz = state.ctx.registry.get(row["clinic_id"]).tz
        local_day = to_local(parse_utc(row["slot"]["start_utc"]), tz).date()
        if doctors and row["slot"]["doctor_id"] not in doctors:
            continue
        if dated and not any(local_day in claim_dates(c, clinic_today(state, row["clinic_id"])) for c in dated):
            continue
        result.append(row)
    return result if (doctors or dated) else candidates


def options_text(state: TurnState, rows: list[dict]) -> str:
    rendered = [
        text(state.lang, "offer.option", n=i, doctor=row["slot"]["doctor_name"], when=f"{when(state, row['slot']['start_utc'], row['clinic_id'])} ({row['ref']})")
        for i, row in enumerate(rows, start=1)
    ]
    return text(state.lang, "list_joiner").join(rendered)


def ask_target(state: TurnState, rows: list[dict]) -> None:
    options = options_text(state, rows)
    state.add("question", "question.target", count=len(rows), options=options)
    data = {"kind": "target", "options": [row["booking_id"] for row in rows], "intent": state.extraction.intent.value, "question": {"key": "question.target", "params": {"count": len(rows), "options": options}}}
    sessions.set_state(state.conn, state.session_id, "awaiting_clarification", data)
    state.session["state"] = "awaiting_clarification"
    state.log("clarification_asked", {"kind": "target", "options": [row["ref"] for row in rows]})


def resolve_target(state: TurnState) -> bool:
    if state.accepted_offer and state.accepted_offer.get("target_booking_id"):
        state.target = verified.get(state.conn, state.accepted_offer["target_booking_id"])
        return True
    if state.target or state.extraction.intent not in NEEDS_TARGET:
        return True
    refs = [c["value"] for c in state.new_claims if c["subject"] == "booking_ref"]
    if refs:
        state.target = verified.by_ref(state.conn, state.customer_id, refs[-1])
        return True
    active = verified.active_for_customer(state.conn, state.customer_id, state.now)
    narrowed = narrow(state, active) if len(active) > 1 else active
    if len(narrowed) <= 1:
        state.target = narrowed[0] if narrowed else None
        return True
    ask_target(state, narrowed)
    return False
