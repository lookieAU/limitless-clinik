from tests.scenarios.scripts import BOOK_THU, STATUS_QUESTION, THU_1500


async def test_status_question_rechecks_clinic_and_never_says_confirmed(make_harness):
    harness = await make_harness({**BOOK_THU, **STATUS_QUESTION})
    await harness.say("Book me Thursday 3pm with Dr A.")
    await harness.admin(f"slots/{THU_1500}/cancel")
    result = await harness.say("Hi — did you confirm my booking?")
    assert "status_recheck" in result["events"] and "clinic_read" in result["events"]
    assert result["events"].index("clinic_read") < len(result["events"])
    assert "confirmed" not in result["reply"].lower()
    assert "cancelled" in result["reply"]
