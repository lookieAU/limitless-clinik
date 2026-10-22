from datetime import date

from agent.llm.types import Intent
from agent.pipeline.conflicts import ClaimView, Conflict, Option, option_matches, view
from agent.pipeline.consent import clinic_today
from agent.pipeline.state import TurnState
from agent.pipeline.templates import text
from agent.repo import claims, sessions, verified
from agent.vocab import DAY_LABEL, WEEK_LABEL, claim_label
from shared.time import week_start


def option_label(state: TurnState, conflict: Conflict, option: Option) -> str:
    lang = "hi" if state.lang == "hi" else "en"
    day_name = DAY_LABEL[lang][conflict.newer.value]
    stamp = f"{option.day.day} {option.day:%b}"
    if option.key == "with_week":
        return text(lang, "label.with_week", day=day_name, week=WEEK_LABEL[lang][conflict.older.value], date=stamp)
    today = clinic_today(state, state.ctx.registry.default().id)
    if week_start(option.day) == week_start(today):
        day_name = f"इस {day_name}" if lang == "hi" else f"this {day_name}"
    return text(lang, "label.standalone", day=day_name, date=stamp)


def serialize(option: Option) -> dict:
    return {
        "key": option.key,
        "keep": option.keep,
        "drop": option.drop,
        "day": option.day.isoformat() if option.day else None,
        "claim": option.claim.__dict__ if option.claim else None,
    }


def deserialize(data: dict) -> Option:
    day = date.fromisoformat(data["day"]) if data["day"] else None
    claim = ClaimView(**data["claim"]) if data["claim"] else None
    return Option(data["key"], data["keep"], data["drop"], day, claim)


def ask_conflict(state: TurnState, conflict: Conflict) -> None:
    if conflict.kind == "ambiguous":
        key, params = "question.dates", {"a": option_label(state, conflict, conflict.options[0]), "b": option_label(state, conflict, conflict.options[1])}
    else:
        older = claims.get(state.conn, conflict.older.id)
        newer = claims.get(state.conn, conflict.newer.id)
        key, params = "question.contradiction", {"older": claim_label(older, state.lang), "newer": claim_label(newer, state.lang)}
    state.add("question", key, **params)
    data = {
        "kind": "claims",
        "conflict": conflict.kind,
        "options": [serialize(option) for option in conflict.options],
        "intent": state.extraction.intent.value,
        "question": {"key": key, "params": params},
    }
    sessions.set_state(state.conn, state.session_id, "awaiting_clarification", data)
    state.session["state"] = "awaiting_clarification"
    state.log("clarification_asked", {"kind": conflict.kind, "question": params})


def pick(state: TurnState, data: dict) -> int | None:
    choice = state.extraction.offer_choice
    if choice and 1 <= choice <= len(data["options"]):
        return choice - 1
    if data["kind"] == "target":
        refs = {c["value"].upper() for c in state.new_claims if c["subject"] == "booking_ref"}
        hits = [i for i, booking_id in enumerate(data["options"]) if (row := verified.get(state.conn, booking_id)) and row["ref"].upper() in refs]
        return hits[0] if len(hits) == 1 else None
    answer = [view(c) for c in state.new_claims]
    today = clinic_today(state, state.ctx.registry.default().id)
    hits = [i for i, raw in enumerate(data["options"]) if option_matches(deserialize(raw), answer, today)]
    return hits[0] if len(hits) == 1 else None


def resolve_pending(state: TurnState) -> bool | None:
    if state.session["state"] != "awaiting_clarification":
        return None
    data = sessions.state_data(state.session)
    index = pick(state, data)
    if index is None:
        question = data["question"]
        state.add("question", question["key"], **question["params"])
        state.log("clarification_asked", {"kind": data["kind"], "repeat": True})
        return False
    if data["kind"] == "target":
        state.target = verified.get(state.conn, data["options"][index])
    else:
        chosen = deserialize(data["options"][index])
        by = state.new_claims[0]["id"] if state.new_claims else "clarification"
        for claim_id in chosen.drop:
            claims.supersede(state.conn, claim_id, by)
        for claim_id in chosen.keep:
            claims.clarify(state.conn, claim_id)
    sessions.set_state(state.conn, state.session_id, "idle")
    state.session["state"] = "idle"
    state.clarified = True
    if state.extraction.intent in (Intent.ANSWER, Intent.CHAT, Intent.ACCEPT):
        state.extraction = state.extraction.model_copy(update={"intent": Intent(data["intent"])})
    state.log("clarification_resolved", {"kind": data["kind"], "choice": index + 1})
    return True
