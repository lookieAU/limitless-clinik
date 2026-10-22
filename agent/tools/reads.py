from datetime import date, time, timedelta

from agent.clinic.observe import observe
from agent.memory.recall import recall
from agent.pipeline.compose import ago, when
from agent.pipeline.policy_gate import CLINIC_ERRORS, Refusal, authorize, check_constraints
from agent.pipeline.state import TurnState
from agent.pipeline.templates import text
from agent.repo import offers, verified
from shared.time import local_to_utc, to_iso_z, to_local

MAX_SLOTS = 12


async def refresh_booking(state: TurnState, booking_id: str) -> dict | None:
    row = verified.get(state.conn, booking_id)
    adapter = state.ctx.registry.get(row["clinic_id"])
    try:
        booking = await adapter.get_booking(booking_id)
    except CLINIC_ERRORS as error:
        state.log("clinic_unreachable", {"booking": row["ref"], "error": str(error)})
        return None
    if booking.customer_id != state.customer_id:
        state.log("authz_denied", {"ref": row["ref"], "stage": "refresh"})
        return None
    observe(state.ctx, booking, "api", "clinic", state.session_id)
    state.log("clinic_read", {"ref": booking.ref, "status": booking.status.value})
    return verified.get(state.conn, booking_id)


def pick_adapter(state: TurnState, clinic_id: str | None):
    if clinic_id and state.ctx.registry.is_enabled(clinic_id):
        return state.ctx.registry.get(clinic_id)
    if state.target:
        return state.ctx.registry.get(state.target["clinic_id"])
    return state.ctx.registry.default()


def slot_summary(state: TurnState, slot) -> dict:
    return {
        "slot_id": slot.id,
        "clinic_id": slot.clinic_id,
        "doctor_id": slot.doctor_id,
        "doctor": slot.doctor_name,
        "when": when(state, to_iso_z(slot.start_utc), slot.clinic_id),
    }


async def check_availability(state: TurnState, args: dict) -> dict:
    adapter = pick_adapter(state, args.get("clinic_id"))
    first = date.fromisoformat(args["date_from"])
    last = date.fromisoformat(args.get("date_to") or args["date_from"])
    start = max(local_to_utc(first, time(0, 0), adapter.tz), state.now)
    end = local_to_utc(last + timedelta(days=1), time(0, 0), adapter.tz)
    earliest = time.fromisoformat(args.get("time_from") or "00:00")
    latest = time.fromisoformat(args.get("time_to") or "23:59")
    slots = await adapter.list_slots(start, end, args.get("doctor_id"))
    observed_at = state.ctx.clock.now()
    matches = []
    for slot in slots:
        local = to_local(slot.start_utc, adapter.tz).time()
        if earliest <= local < latest:
            state.slot_obs[slot.id] = (slot, observed_at)
            matches.append(slot_summary(state, slot))
    return {"ok": True, "clinic_id": adapter.id, "slots": matches[:MAX_SLOTS], "total": len(matches), "checked_at": to_iso_z(observed_at)}


async def propose_slot(state: TurnState, args: dict) -> dict:
    slot_id = args["slot_id"]
    observed = state.slot_obs.get(slot_id)
    if observed is None or not observed[0].available:
        raise Refusal("check_availability_first", "only offer slots returned by check_availability this turn")
    check_constraints(state, observed[0])
    action = args.get("action") or ("reschedule" if state.target else "book")
    state.proposals.append((observed[0], action))
    return {"ok": True, "offered": slot_id, "action": action, "note": "the system shows the offer; wait for the customer"}


async def get_booking(state: TurnState, args: dict) -> dict:
    row = await authorize(state, args.get("booking_ref"), write=False)
    fresh = await refresh_booking(state, row["booking_id"])
    if fresh is None:
        state.add("fallback", "fallback.unreachable")
        return {"ok": False, "error": "clinic_unreachable"}
    state.add("status", "status", booking_id=fresh["booking_id"])
    return {"ok": True, "ref": fresh["ref"], "status": fresh["status"], "note": "the system shows the verified status line"}


async def recall_tool(state: TurnState, args: dict) -> dict:
    items = recall(state.ctx, state.user["id"], args["query"], int(args.get("k") or 5))
    return {"ok": True, "items": items, "note": "these are things the CUSTOMER said (claims), not clinic facts"}


def offer_segments(state: TurnState) -> None:
    if not state.proposals:
        return
    slots = [slot for slot, _ in state.proposals]
    action = state.proposals[-1][1]
    target = state.target["booking_id"] if state.target and action == "reschedule" else None
    offers.replace_offers(state.conn, state.session_id, slots, action, target, state.ctx.clock.now())
    checked = ago(state.lang, state.ctx.clock.now(), state.ctx.clock.now())
    if len(slots) == 1:
        summary = slot_summary(state, slots[0])
        verb = text(state.lang, f"verb.{action}")
        state.add("offer", "offer.single", doctor=summary["doctor"], when=summary["when"], ago=checked, verb=verb)
        return
    state.add("offer", "offer.list", options=option_list(state, slots), ago=checked)


def option_list(state: TurnState, slots) -> str:
    rendered = [
        text(state.lang, "offer.option", n=index, doctor=slot.doctor_name, when=slot_summary(state, slot)["when"])
        for index, slot in enumerate(slots, start=1)
    ]
    return text(state.lang, "list_joiner").join(rendered)
