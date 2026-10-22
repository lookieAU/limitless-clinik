from datetime import timedelta

from agent.notices import mark_delivered, undelivered
from agent.pipeline.compose import ago
from agent.pipeline.conflicts import candidate_dates, view
from agent.pipeline.consent import violated_constraint
from agent.pipeline.policy_gate import CLINIC_ERRORS, refresh_customer
from agent.pipeline.state import TurnState
from agent.pipeline.verify_reply import prose_violations, stale_bookings
from agent.repo import claims, offers, verified
from agent.tools.reads import option_list, refresh_booking
from shared.time import parse_utc, to_local

REBOOK_DAYS = 14
REBOOK_OPTIONS = 3


def relevant_bookings(state: TurnState) -> list[dict]:
    if state.target:
        return [state.target]
    rows = verified.for_customer(state.conn, state.customer_id)
    return [row for row in rows if parse_utc(row["slot"]["start_utc"]) > state.now]


async def status_recheck(state: TurnState) -> None:
    state.log("status_recheck", {"target": state.target["ref"] if state.target else None})
    rows = relevant_bookings(state)
    if not rows:
        await refresh_customer(state)
        rows = relevant_bookings(state)
    if not rows:
        state.add("info", "none.bookings", ago=ago(state.lang, state.ctx.clock.now(), state.ctx.clock.now()))
        return
    for row in rows:
        fresh = await refresh_booking(state, row["booking_id"])
        if fresh:
            state.add("status", "status", booking_id=fresh["booking_id"])
        else:
            state.add("fallback", "fallback.unreachable")


async def rebooking_offers(state: TurnState, booking_row: dict) -> None:
    adapter = state.ctx.registry.get(booking_row["clinic_id"])
    cancelled_start = parse_utc(booking_row["slot"]["start_utc"])
    try:
        slots = await adapter.list_slots(state.now, state.now + timedelta(days=REBOOK_DAYS), booking_row["slot"]["doctor_id"])
    except CLINIC_ERRORS:
        return
    wall = to_local(cancelled_start, adapter.tz).time()
    allowed = set(candidate_dates([view(c) for c in claims.live_for_user(state.conn, state.user["id"]) if c["polarity"] == "negative"], to_local(state.now, adapter.tz).date()))
    choices = [
        slot for slot in slots
        if slot.available and to_local(slot.start_utc, adapter.tz).date() in allowed and not violated_constraint(state, slot)
    ]
    choices.sort(key=lambda slot: (to_local(slot.start_utc, adapter.tz).time() != wall, slot.start_utc))
    picked = sorted(choices[:REBOOK_OPTIONS], key=lambda slot: slot.start_utc)
    if not picked:
        return
    observed = state.ctx.clock.now()
    for slot in picked:
        state.slot_obs[slot.id] = (slot, observed)
    offers.replace_offers(state.conn, state.session_id, picked, "book", None, observed)
    state.add("offer", "offer.rebook", options=option_list(state, picked), ago=ago(state.lang, observed, observed))


async def deliver_notices(state: TurnState) -> None:
    pending = undelivered(state.conn, state.user["id"])
    for notice in pending:
        state.add("notice", f"notice.{notice['template_key']}", booking_id=notice["booking_id"], **notice["params"])
    if not pending:
        return
    mark_delivered(state.conn, [notice["id"] for notice in pending], state.ctx.clock.now())
    state.log("notices_delivered", {"count": len(pending)})
    for notice in pending:
        if notice["template_key"] == "booking_cancelled":
            row = verified.get(state.conn, notice["booking_id"])
            if row and row["status"] == "cancelled":
                await rebooking_offers(state, row)


async def enforce_truth(state: TurnState, regenerate) -> None:
    for booking_id in stale_bookings(state):
        if await refresh_booking(state, booking_id) is None:
            state.segments = [s for s in state.segments if s.booking_id != booking_id]
            state.add("fallback", "fallback.unreachable")
            state.log("reply_blocked", {"reason": "stale_unrefreshable", "booking": booking_id})
    hits = prose_violations(state.prose)
    if not hits:
        return
    state.log("reply_blocked", {"reason": "unverified_status_in_prose", "words": hits, "prose": state.prose})
    if not state.has("status") and not state.has("action"):
        await status_recheck(state)
    state.prose = await regenerate(state)
    if prose_violations(state.prose):
        state.log("reply_blocked", {"reason": "regenerated_prose_still_unverified", "prose": state.prose})
        state.prose = ""
        state.add("fallback", "fallback.checking")
