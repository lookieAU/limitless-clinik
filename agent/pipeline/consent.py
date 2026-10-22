from agent.pipeline.conflicts import candidate_dates, claim_dates, exact_time, view
from agent.pipeline.state import TurnState
from agent.repo import claims, offers
from agent.vocab import WEEKDAYS
from shared.time import to_local
from shared.types import Slot


def live_views(state: TurnState):
    return [view(row) for row in claims.live_for_session(state.conn, state.session_id)]


def clinic_today(state: TurnState, clinic_id: str):
    return to_local(state.now, state.ctx.registry.get(clinic_id).tz).date()


def named_slot(state: TurnState, slot: Slot) -> bool:
    if not state.new_claims and not state.clarified:
        return False
    live = live_views(state)
    dates = candidate_dates(live, clinic_today(state, slot.clinic_id))
    wall = exact_time(live)
    if len(dates) != 1 or wall is None:
        return False
    local = to_local(slot.start_utc, state.ctx.registry.get(slot.clinic_id).tz)
    if local.date() != dates[0] or local.time().replace(second=0, microsecond=0) != wall:
        return False
    doctors = [c.value for c in live if c.subject == "doctor" and c.polarity == "positive"]
    return not doctors or doctors[-1] == slot.doctor_id


def violated_constraint(state: TurnState, slot: Slot) -> dict | None:
    local = to_local(slot.start_utc, state.ctx.registry.get(slot.clinic_id).tz)
    today = clinic_today(state, slot.clinic_id)
    for claim in claims.live_for_user(state.conn, state.user["id"]):
        if claim["polarity"] != "negative":
            continue
        subject, value = claim["subject"], claim["value"]
        if subject == "day" and WEEKDAYS[local.weekday()] == value:
            return claim
        if subject in ("date", "week") and local.date() in claim_dates(view(claim), today):
            return claim
        if subject == "doctor" and slot.doctor_id == value:
            return claim
    return None


def accept_offer(state: TurnState) -> None:
    open_offers = offers.open_offers(state.conn, state.session_id)
    if not open_offers:
        return
    if state.extraction.intent == "decline_offer":
        offers.close_open(state.conn, state.session_id, "declined")
        state.log("offer_declined", {"count": len(open_offers)})
        return
    if state.extraction.intent != "accept_offer":
        return
    choice = state.extraction.offer_choice or (1 if len(open_offers) == 1 else None)
    if choice and 1 <= choice <= len(open_offers):
        state.accepted_offer = open_offers[choice - 1]
        state.log("offer_accepted", {"slot_id": state.accepted_offer["slot_id"], "action": state.accepted_offer["action"]})
