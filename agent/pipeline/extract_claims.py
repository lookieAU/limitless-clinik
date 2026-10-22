import re

from agent.llm.types import ClaimDraft, Extraction, ExtractRequest
from agent.pipeline.state import TurnState
from agent.repo import claims, messages, offers
from agent.vocab import DAY_FORMS, WEEKDAYS
from shared.time import to_local

VALUE_PATTERNS = {
    "day": r"(mon|tue|wed|thu|fri|sat|sun)",
    "date": r"\d{4}-\d{2}-\d{2}",
    "time_window": r"((before|after)_)?([01]\d|2[0-3]):[0-5]\d",
    "week": r"(this_week|next_week)",
    "doctor": r"dr_[a-z]+",
    "booking_ref": r"[A-Za-z]{2}-\d{4}",
    "clinic": r"clinic_[a-z]+",
}


def squash(text: str) -> str:
    return " ".join(text.casefold().split())


def grounded(draft: ClaimDraft, text: str, doctors: dict[str, str]) -> str | None:
    if not re.fullmatch(VALUE_PATTERNS[draft.subject], draft.value):
        return "bad_value"
    if squash(draft.raw_span) not in squash(text):
        return "span_not_in_message"
    if draft.subject == "day":
        forms = [form for forms in DAY_FORMS[draft.value].values() for form in forms]
        if not any(form in squash(draft.raw_span) for form in forms):
            return "span_does_not_name_day"
    if draft.subject == "doctor" and draft.value not in doctors:
        return "unknown_doctor"
    return None


def extraction_context(state: TurnState, doctors: dict[str, str]) -> str:
    adapter = state.ctx.registry.default()
    local = to_local(state.now, adapter.tz)
    history = "\n".join(f"{m['role']}: {m['text']}" for m in messages.recent(state.conn, state.session_id, 6)[:-1])
    open_offers = offers.open_offers(state.conn, state.session_id)
    offered = "; ".join(f"{i}) {o['slot']['doctor_name']} {o['slot']['start_utc']}" for i, o in enumerate(open_offers, 1))
    return (
        f"Today in clinic time ({adapter.policy.tz}): {WEEKDAYS[local.weekday()]} {local.date().isoformat()} {local:%H:%M}.\n"
        f"Doctors: {', '.join(f'{k}={v}' for k, v in doctors.items())}.\n"
        f"Enabled clinics: {', '.join(a.id for a in state.ctx.registry.enabled())}.\n"
        f"Session state: {state.session['state']}. Open offers: {offered or 'none'}.\n"
        f"Recent conversation:\n{history or '(none)'}"
    )


async def extract(state: TurnState) -> None:
    doctors = await state.ctx.doctor_names()
    request = ExtractRequest(
        turn_key=state.message_id, text=state.text, lang=state.lang, context=extraction_context(state, doctors)
    )
    try:
        extraction = await state.ctx.llm.extract(request)
    except Exception as error:
        state.log("extract_failed", {"error": str(error)})
        extraction = Extraction()
    kept = []
    for draft in extraction.claims:
        problem = grounded(draft, state.text, doctors)
        if problem:
            state.log("claim_rejected", {"subject": draft.subject, "value": draft.value, "reason": problem})
            continue
        kept.append(draft)
    state.extraction = extraction.model_copy(update={"claims": kept})
    for draft in kept:
        row = claims.insert_claim(
            state.conn, state.user["id"], state.session_id, state.message_id, draft.model_dump(), state.lang, state.now
        )
        state.new_claims.append(row)
    if kept:
        state.log("claims_extracted", {"count": len(kept), "intent": extraction.intent.value})
