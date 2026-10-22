from datetime import timedelta

import pytest

from agent.pipeline.policy_gate import Refusal, check_budget, check_session, consent
from agent.pipeline.state import TurnState
from agent.repo import claims, sessions, users
from shared.types import Slot

THU = "2026-11-05T09:30:00Z"


def make_state(harness, drafts: list[dict]) -> TurnState:
    ctx = harness.agent_ctx
    user = users.get_user(ctx.conn, "u_asha")
    session = sessions.create_session(ctx.conn, user, ctx.clock.now())
    state = TurnState(ctx=ctx, user=user, session=session, message_id="m1", text="", lang="en", now=ctx.clock.now())
    for draft in drafts:
        state.new_claims.append(claims.insert_claim(ctx.conn, user["id"], session["id"], "m1", {"kind": "preference", "polarity": "positive", **draft}, "en", ctx.clock.now()))
    return state


def slot(start: str = THU, doctor: str = "dr_a") -> Slot:
    from shared.time import parse_utc

    begin = parse_utc(start)
    return Slot(id=f"{doctor}_x", clinic_id="clinic_a", doctor_id=doctor, doctor_name="Dr", start_utc=begin, end_utc=begin + timedelta(minutes=30))


async def test_exact_named_slot_has_consent(make_harness):
    harness = await make_harness()
    state = make_state(harness, [{"subject": "day", "value": "thu", "raw_span": "Thu"}, {"subject": "time_window", "value": "15:00", "raw_span": "3pm"}])
    assert consent(state, slot(), "book") == "named"


async def test_window_is_not_consent(make_harness):
    harness = await make_harness()
    state = make_state(harness, [{"subject": "day", "value": "thu", "raw_span": "Thu"}, {"subject": "time_window", "value": "before_16:00", "raw_span": "before 4"}])
    with pytest.raises(Refusal) as refusal:
        consent(state, slot(), "book")
    assert refusal.value.code == "consent_required"


async def test_wrong_doctor_is_not_consent(make_harness):
    harness = await make_harness()
    drafts = [{"subject": "day", "value": "thu", "raw_span": "Thu"}, {"subject": "time_window", "value": "15:00", "raw_span": "3pm"}, {"subject": "doctor", "value": "dr_b", "raw_span": "Dr B"}]
    with pytest.raises(Refusal):
        consent(make_state(harness, drafts), slot(), "book")


async def test_one_write_per_turn_and_clarification_lock(make_harness):
    harness = await make_harness()
    state = make_state(harness, [])
    state.writes = 1
    with pytest.raises(Refusal):
        check_budget(state)
    state.session["state"] = "awaiting_clarification"
    with pytest.raises(Refusal):
        check_session(state)
