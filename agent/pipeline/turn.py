from pydantic import BaseModel

from agent.llm.types import Intent
from agent.pipeline import compose
from agent.pipeline.clarify import ask_conflict, resolve_pending
from agent.pipeline.conflicts import apply_claims, view
from agent.pipeline.consent import accept_offer, clinic_today
from agent.pipeline.extract_claims import extract
from agent.pipeline.injection import scan
from agent.pipeline.language import detect_language
from agent.pipeline.planner import plan, regenerate
from agent.pipeline.resolve_target import resolve_target
from agent.pipeline.state import TurnState
from agent.pipeline.status import deliver_notices, drop_repeated_prose, enforce_truth, status_recheck
from agent.pipeline.sync import needs_sync, sync_customer
from agent.repo import claims, messages, sessions


class TurnResult(BaseModel):
    reply: str
    lang: str
    facts: list[dict]
    events: list[str]
    segments: list[dict]
    session_state: str
    message_id: str
    prose: str = ""
    system_text: str = ""
    chips: list[dict] = []
    tools: list[str] = []


def apply_new_claims(state: TurnState) -> bool:
    new_ids = {c["id"] for c in state.new_claims}
    active = [view(c) for c in claims.live_for_session(state.conn, state.session_id) if c["id"] not in new_ids]
    today = clinic_today(state, state.ctx.registry.default().id)
    outcome = apply_claims(active, [view(c) for c in state.new_claims], today, detect=not state.clarified)
    for old_id, new_id in outcome.superseded:
        claims.supersede(state.conn, old_id, new_id)
    if outcome.conflict:
        ask_conflict(state, outcome.conflict)
        return False
    return True


async def begin(ctx, user: dict, session: dict, text: str, client_msg_id: str | None) -> TurnState:
    now = ctx.clock.now()
    lang = detect_language(text, session.get("lang") or user["preferred_lang"])
    message_id = messages.add_message(ctx.conn, session["id"], "customer", text, lang, now, client_msg_id)
    state = TurnState(ctx=ctx, user=user, session=dict(session), message_id=message_id, text=text, lang=lang, now=now)
    state.injection = scan(text)
    if state.injection.flagged:
        state.log("injection_flag", {"reasons": list(state.injection.reasons), "excerpt": text[:200]})
    if needs_sync(ctx, session):
        await sync_customer(ctx, user, session["id"])
        state.events.append("session_sync")
    return state


async def understand(state: TurnState, recap: bool) -> bool:
    await deliver_notices(state)
    await extract(state)
    if recap and state.extraction.intent == Intent.CHAT:
        state.extraction = state.extraction.model_copy(update={"intent": Intent.STATUS})
    pending = resolve_pending(state)
    if pending is False:
        return False
    if not apply_new_claims(state):
        return False
    accept_offer(state)
    if not resolve_target(state):
        return False
    if state.extraction.intent == "status_query":
        await status_recheck(state)
    return True


async def finish(state: TurnState) -> TurnResult:
    if state.injection and state.injection.bulk and state.writes == 0:
        state.add("refusal", "refusal.bulk")
    await enforce_truth(state, regenerate)
    drop_repeated_prose(state, compose.system_text(state))
    if not state.segments and not state.prose.strip():
        state.add("info", "help.default")
    reply = compose.render(state)
    session = sessions.get_session(state.conn, state.session_id)
    result = TurnResult(
        reply=reply,
        lang=state.lang,
        facts=compose.facts(state),
        events=state.events,
        segments=[{"kind": s.kind, "key": s.key, "booking_id": s.booking_id} for s in state.segments],
        session_state=session["state"],
        message_id=state.message_id,
        prose=state.prose.strip(),
        system_text=compose.system_text(state),
        chips=compose.chips(state),
        tools=list(dict.fromkeys(state.tools)),
    )
    messages.add_message(state.conn, state.session_id, "agent", reply, state.lang, state.ctx.clock.now())
    messages.store_result(state.conn, state.message_id, result.model_dump())
    sessions.touch(state.conn, state.session_id, state.ctx.clock.now(), state.lang)
    state.ctx.bus.publish(state.user["id"], "panels")
    return result


async def turn(ctx, user: dict, session: dict, text: str, client_msg_id: str | None = None, recap: bool = False) -> TurnResult:
    prior = messages.prior_result(ctx.conn, session["id"], client_msg_id)
    if prior:
        return TurnResult(**prior)
    state = await begin(ctx, user, session, text, client_msg_id)
    if await understand(state, recap):
        await plan(state)
    return await finish(state)
