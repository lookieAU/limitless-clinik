import json
from collections.abc import Awaitable, Callable

from agent import outbox
from agent.clinic.adapter import ClinicAdapter, ClinicFailure, ClinicTimeout
from agent.clinic.observe import observe
from agent.pipeline.compose import when
from agent.pipeline.policy_gate import (
    CLINIC_ERRORS,
    Refusal,
    authorize,
    check_budget,
    check_constraints,
    check_cutoff,
    check_limits,
    check_session,
    consent,
    fresh_slot,
)
from agent.pipeline.state import TurnState
from agent.repo import claims, offers
from shared.ids import idempotency_key
from shared.time import to_iso_z
from shared.types import Booking, BookingStatus

Perform = Callable[[], Awaitable[list[Booking]]]


def intent_id(state: TurnState) -> str:
    return state.accepted_offer["id"] if state.accepted_offer else state.message_id


async def reconcile(state: TurnState, adapter: ClinicAdapter, action: str, key: str, slot_id: str | None) -> list[Booking] | None:
    try:
        return await adapter.reconcile_key(action, key)
    except ClinicTimeout:
        return None
    except ClinicFailure:
        pass
    try:
        bookings = await adapter.bookings_for_customer(state.customer_id)
    except CLINIC_ERRORS:
        return None
    return [b for b in bookings if slot_id and b.slot.id == slot_id and b.status == BookingStatus.CONFIRMED]


async def execute(
    state: TurnState, adapter: ClinicAdapter, action: str, payload: dict, key: str, perform: Perform
) -> list[Booking]:
    now = state.ctx.clock.now()
    row = outbox.begin(state.conn, state.user["id"], action, payload, key, intent_id(state), now)
    if row["state"] == "succeeded":
        state.log("outbox_replay", {"action": action, "key": key[:12]})
        return [Booking(**item) for item in json.loads(row["result_json"])["bookings"]]
    outbox.mark(state.conn, row["id"], "in_flight", now)
    state.writes += 1
    state.log("clinic_write", {"action": action, "key": key[:12], **payload})
    try:
        bookings = await perform()
    except ClinicTimeout:
        bookings = await recover(state, adapter, action, payload, key, row["id"], perform)
    except ClinicFailure as failure:
        outbox.mark(state.conn, row["id"], "failed", state.ctx.clock.now(), {"error": failure.code})
        raise refusal_for(failure) from failure
    outbox.mark(state.conn, row["id"], "succeeded", state.ctx.clock.now(), {"bookings": [b.model_dump(mode="json") for b in bookings]})
    return bookings


async def recover(
    state: TurnState, adapter: ClinicAdapter, action: str, payload: dict, key: str, row_id: str, perform: Perform
) -> list[Booking]:
    outbox.mark(state.conn, row_id, "unknown", state.ctx.clock.now())
    state.add("uncertain", "uncertain.write")
    state.log("write_unknown", {"action": action})
    found = await reconcile(state, adapter, action, key, payload.get("slot_id"))
    if found:
        state.add("uncertain", "uncertain.found")
        state.log("reconciled", {"found": True})
        return found
    if found is None:
        state.add("uncertain", "uncertain.unknown")
        raise Refusal("write_unknown", "clinic not answering; do not retry, the system will reconcile")
    state.add("uncertain", "uncertain.retried")
    state.log("reconciled", {"found": False, "retry": "same_key"})
    try:
        return await perform()
    except ClinicTimeout as error:
        state.add("uncertain", "uncertain.unknown")
        raise Refusal("write_unknown", "clinic not answering; do not retry") from error
    except ClinicFailure as failure:
        outbox.mark(state.conn, row_id, "failed", state.ctx.clock.now(), {"error": failure.code})
        raise refusal_for(failure) from failure


def refusal_for(failure: ClinicFailure) -> Refusal:
    if failure.code in ("slot_unavailable", "cancel_cutoff"):
        return Refusal(failure.code, failure.detail)
    return Refusal("clinic_error", failure.detail, code=failure.code)


def record(state: TurnState, bookings: list[Booking], segment_key: str) -> dict:
    for booking in bookings:
        observe(state.ctx, booking, "api", "agent", state.session_id)
    primary = next((b for b in bookings if b.status == BookingStatus.CONFIRMED), bookings[0])
    if primary.status == BookingStatus.CONFIRMED:
        claims.hint_booking(state.conn, state.session_id, primary.id)
    if state.accepted_offer:
        offers.set_status(state.conn, state.accepted_offer["id"], "accepted")
    offers.close_open(state.conn, state.session_id, "superseded")
    state.add("action", segment_key, booking_id=primary.id)
    return {
        "ok": True,
        "ref": primary.ref,
        "status": primary.status.value,
        "when": when(state, to_iso_z(primary.slot.start_utc), primary.clinic_id),
        "note": "the system shows the verified confirmation line; do not restate status",
    }


async def book(state: TurnState, args: dict) -> dict:
    check_session(state)
    check_budget(state)
    slot, adapter = await fresh_slot(state, args["slot_id"])
    consent(state, slot, "book")
    check_constraints(state, slot)
    check_limits(state, adapter)
    key = idempotency_key(state.user["id"], "book", slot.id, intent_id(state))
    bookings = await execute(state, adapter, "book", {"clinic_id": adapter.id, "slot_id": slot.id}, key, lambda: adapter.book(state.customer_id, slot.id, key))
    return record(state, bookings, "action.booked")


async def reschedule(state: TurnState, args: dict) -> dict:
    check_session(state)
    check_budget(state)
    row = await authorize(state, args.get("booking_ref"), write=True)
    adapter = state.ctx.registry.get(row["clinic_id"])
    if adapter.policy.reschedule_mode == "cancel_and_rebook":
        check_cutoff(state, adapter, row)
    slot, slot_adapter = await fresh_slot(state, args["slot_id"])
    if slot_adapter.id != adapter.id:
        raise Refusal("cross_clinic_move", "book at the other clinic and cancel separately")
    consent(state, slot, "reschedule")
    check_constraints(state, slot)
    current = Booking(**{**row, "id": row["booking_id"], "slot": row["slot"]})
    key = idempotency_key(state.user["id"], "reschedule", f"{row['booking_id']}->{slot.id}", intent_id(state))
    payload = {"clinic_id": adapter.id, "booking": row["ref"], "slot_id": slot.id}
    bookings = await execute(state, adapter, "reschedule", payload, key, lambda: adapter.reschedule(current, slot.id, key))
    return record(state, bookings, "action.rescheduled")


async def cancel(state: TurnState, args: dict) -> dict:
    check_session(state)
    check_budget(state)
    row = await authorize(state, args.get("booking_ref"), write=True)
    if state.extraction.intent != "cancel":
        raise Refusal("consent_required", "the customer has not asked to cancel in this message")
    adapter = state.ctx.registry.get(row["clinic_id"])
    check_cutoff(state, adapter, row)
    current = Booking(**{**row, "id": row["booking_id"], "slot": row["slot"]})
    key = idempotency_key(state.user["id"], "cancel", row["booking_id"], intent_id(state))
    bookings = await execute(state, adapter, "cancel", {"clinic_id": adapter.id, "booking": row["ref"]}, key, lambda: adapter.cancel(current, key))
    return record(state, bookings, "action.cancelled")
