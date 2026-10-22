from tests.scenarios.scripts import BOOK_THU, NEXT_WEEK_THEN_THURSDAY


async def test_next_week_then_thursday_asks_one_question(make_harness):
    harness = await make_harness({**BOOK_THU, **NEXT_WEEK_THEN_THURSDAY})
    await harness.say("Book me Thursday 3pm with Dr A.")
    await harness.say("Can you move it to next week?")
    writes_before = harness.clinic_writes()
    result = await harness.say("Thursday is fine.")
    assert harness.clinic_writes() == writes_before
    assert result["reply"].count("?") == 1
    assert "12 Nov" in result["reply"] and "5 Nov" in result["reply"]
    assert result["session_state"] == "awaiting_clarification"
    assert len(harness.events("clarification_asked")) == 1
    assert harness.clinic_bookings()[0]["slot_id"] == "dr_a_20261105_1500"
