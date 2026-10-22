from agent.tools.reads import check_availability
from tests.unit.test_policy_gate import make_state


async def test_exact_time_query_returns_that_slot(make_harness):
    harness = await make_harness()
    state = make_state(harness, [])
    result = await check_availability(state, {"doctor_id": "dr_a", "date_from": "2026-11-05", "time_from": "15:00", "time_to": "15:00"})
    assert [slot["slot_id"] for slot in result["slots"]] == ["dr_a_20261105_1500"]


async def test_whole_day_keeps_slots_near_the_stated_time(make_harness):
    harness = await make_harness()
    state = make_state(harness, [{"subject": "time_window", "value": "15:00", "raw_span": "3pm"}])
    result = await check_availability(state, {"doctor_id": "dr_a", "date_from": "2026-11-05"})
    ids = [slot["slot_id"] for slot in result["slots"]]
    assert "dr_a_20261105_1500" in ids and "dr_a_20261105_1630" in ids
    assert ids == sorted(ids) and result["total"] == 16
