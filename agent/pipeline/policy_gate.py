from datetime import timedelta

import httpx

from agent.clinic.adapter import ClinicAdapter, ClinicFailure, ClinicTimeout
from agent.clinic.observe import observe
from agent.pipeline.consent import named_slot, violated_constraint
from agent.pipeline.state import TurnState
from agent.repo import offers, verified
from agent.vocab import claim_label
from shared.time import parse_utc
from shared.types import Slot

SEGMENT_CODES = ("authz_denied", "cancel_cutoff", "active_limit", "slot_unavailable")
CLINIC_ERRORS = (ClinicTimeout, ClinicFailure, httpx.HTTPError)


class Refusal(Exception):
    def __init__(self, code: str, detail: str = "", **params):
        super().__init__(code)
        self.code = code
        self.detail = detail
        self.params = params


def check_session(state: TurnState) -> None:
    if state.session["state"] == "awaiting_clarification":
        raise Refusal("clarification_pending", "wait for the customer's answer to the clarifying question")


def check_budget(state: TurnState) -> None:
    if state.writes >= 1:
        raise Refusal("one_write_per_turn", "only one booking change is allowed per customer message")


async def refresh_customer(state: TurnState) -> bool:
    ok = True
    for adapter in state.ctx.registry.enabled():
        try:
            for booking in await adapter.bookings_for_customer(state.customer_id):
                observe(state.ctx, booking, "api", "clinic", state.session_id)
        except CLINIC_ERRORS as error:
            ok = False
            state.log("clinic_unreachable", {"clinic": adapter.id, "error": str(error)})
    return ok


async def authorize(state: TurnState, booking_ref: str | None, write: bool) -> dict:
    if booking_ref:
        row = verified.by_ref(state.conn, state.customer_id, booking_ref)
        if row is None:
            await refresh_customer(state)
            row = verified.by_ref(state.conn, state.customer_id, booking_ref)
    else:
        row = state.target
        if row is None:
            raise Refusal("target_required", "say which booking (by ref) this is about")
    if row is None or row["customer_id"] != state.customer_id:
        state.log("authz_denied", {"ref": booking_ref, "write": write})
        raise Refusal("authz_denied")
    if not write:
        return row
    adapter = state.ctx.registry.get(row["clinic_id"])
    try:
        fresh = await adapter.get_booking(row["booking_id"])
    except CLINIC_ERRORS as error:
        raise Refusal("clinic_unreachable", str(error)) from error
    if fresh.customer_id != state.customer_id:
        state.log("authz_denied", {"ref": booking_ref, "write": write, "stage": "clinic"})
        raise Refusal("authz_denied")
    observe(state.ctx, fresh, "api", "clinic", state.session_id)
    row = verified.get(state.conn, fresh.id)
    if row["status"] != "confirmed":
        raise Refusal("booking_not_active", f"booking {row['ref']} is {row['status']} at the clinic")
    return row


def consent(state: TurnState, slot: Slot, action: str) -> str:
    offer = state.accepted_offer
    if offer and offer["slot_id"] == slot.id and offer["action"] == action:
        return "offer"
    if named_slot(state, slot):
        return "named"
    raise Refusal("consent_required", "the customer has not chosen this exact slot; use propose_slot and wait for a yes")


def check_constraints(state: TurnState, slot: Slot) -> None:
    claim = violated_constraint(state, slot)
    if claim:
        raise Refusal("conflicts_with_customer_constraint", f"customer said {claim_label(claim, 'en')}")


def check_limits(state: TurnState, adapter: ClinicAdapter) -> None:
    active = [row for row in verified.active_for_customer(state.conn, state.customer_id, state.now) if row["clinic_id"] == adapter.id]
    limit = adapter.policy.max_active_bookings_per_customer
    if len(active) >= limit:
        raise Refusal("active_limit", f"limit {limit}", clinic=adapter.policy.name, limit=limit)


def check_cutoff(state: TurnState, adapter: ClinicAdapter, row: dict) -> None:
    hours = adapter.policy.customer_cancel_cutoff_hours
    if hours and parse_utc(row["slot"]["start_utc"]) - state.now < timedelta(hours=hours):
        raise Refusal("cancel_cutoff", f"{hours}h notice required", clinic=adapter.policy.name, hours=hours)


def known_slot(state: TurnState, slot_id: str) -> Slot | None:
    if slot_id in state.slot_obs:
        return state.slot_obs[slot_id][0]
    for offer in offers.open_offers(state.conn, state.session_id):
        if offer["slot_id"] == slot_id:
            return Slot(**offer["slot"])
    return None


async def fresh_slot(state: TurnState, slot_id: str) -> tuple[Slot, ClinicAdapter]:
    slot = known_slot(state, slot_id)
    if slot is None:
        raise Refusal("check_availability_first", "look the slot up with check_availability first")
    adapter = state.ctx.registry.get(slot.clinic_id)
    observed = state.slot_obs.get(slot_id)
    ttl = timedelta(seconds=state.ctx.settings.freshness_ttl_s)
    if observed and state.ctx.clock.now() - observed[1] <= ttl and observed[0].available:
        return observed[0], adapter
    try:
        window = await adapter.list_slots(slot.start_utc - timedelta(minutes=1), slot.end_utc, slot.doctor_id)
    except CLINIC_ERRORS as error:
        raise Refusal("clinic_unreachable", str(error)) from error
    match = next((item for item in window if item.id == slot_id and item.available), None)
    if match is None:
        raise Refusal("slot_unavailable", "slot is no longer free")
    state.slot_obs[slot_id] = (match, state.ctx.clock.now())
    return match, adapter
