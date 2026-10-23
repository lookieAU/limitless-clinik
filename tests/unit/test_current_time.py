from agent.tools.reads import current_time
from tests.unit.test_policy_gate import make_state


async def test_current_time_reports_clinic_and_customer_clocks(make_harness):
    harness = await make_harness()
    state = make_state(harness, [])
    result = await current_time(state, {})
    assert result["today"] == "2026-11-02" and result["weekday"] == "Monday"
    assert result["clinic_time"] == "Mon 02 Nov 2026, 9:00 am IST"
