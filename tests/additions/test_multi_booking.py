from tests.scenarios.scripts import BOOK_THU, FRI_0900, call, claim

BOOK_FRI = {
    "Also book Friday 9am with Dr A.": {
        "extract": {"intent": "book", "claims": [claim("day", "fri", "Friday"), claim("time_window", "09:00", "9am"), claim("doctor", "dr_a", "Dr A")]},
        "steps": [call("check_availability", doctor_id="dr_a", date_from="2026-11-06"), call("book", slot_id=FRI_0900), {"text": "Both are set up."}],
    },
    "Move my appointment please.": {"extract": {"intent": "reschedule"}, "steps": [call("reschedule", slot_id="dr_a_20261106_1000")]},
    "The Friday one.": {"extract": {"intent": "clarification_answer", "claims": [claim("day", "fri", "Friday")]}, "steps": [{"text": "Got it — which new time?"}]},
}


async def test_ambiguous_target_asks_once_and_locks_writes(make_harness):
    harness = await make_harness({**BOOK_THU, **BOOK_FRI})
    await harness.say("Book me Thursday 3pm with Dr A.")
    await harness.say("Also book Friday 9am with Dr A.")
    assert len(harness.clinic_bookings()) == 2
    writes = harness.clinic_writes()
    result = await harness.say("Move my appointment please.")
    assert harness.clinic_writes() == writes
    assert "You have 2 upcoming appointments" in result["reply"] and result["reply"].count("?") == 1
    assert result["session_state"] == "awaiting_clarification"
    answer = await harness.say("The Friday one.")
    assert answer["session_state"] == "idle"
    assert "clarification_resolved" in answer["events"]


async def test_new_request_moves_past_an_unanswered_question(make_harness):
    from tests.scenarios.scripts import NEXT_WEEK_THEN_THURSDAY

    script = {**BOOK_THU, **NEXT_WEEK_THEN_THURSDAY, "Book me Friday 9am with Dr A.": {
        "extract": {"intent": "book", "claims": [claim("day", "fri", "Friday"), claim("time_window", "09:00", "9am"), claim("doctor", "dr_a", "Dr A")]},
        "steps": [call("check_availability", doctor_id="dr_a", date_from="2026-11-06"), call("book", slot_id=FRI_0900)],
    }}
    harness = await make_harness(script)
    await harness.say("Book me Thursday 3pm with Dr A.")
    await harness.say("Can you move it to next week?")
    asked = await harness.say("Thursday is fine.")
    assert asked["session_state"] == "awaiting_clarification"
    moved_on = await harness.say("Book me Friday 9am with Dr A.")
    assert "clarification_abandoned" in moved_on["events"] and "Just to be sure" not in moved_on["reply"]
