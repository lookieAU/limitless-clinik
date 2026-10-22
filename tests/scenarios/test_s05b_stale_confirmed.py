from tests.scenarios.scripts import BOOK_THU, THU_1500

LYING_LLM = {
    "Is everything good for Thursday?": {
        "extract": {"intent": "chat"},
        "steps": [{"text": "Yes — your booking is confirmed, see you Thursday!"}, {"text": "Here's the latest from the clinic."}],
    }
}


async def test_unverified_confirmed_is_blocked_and_rechecked(make_harness):
    harness = await make_harness({**BOOK_THU, **LYING_LLM})
    await harness.say("Book me Thursday 3pm with Dr A.")
    await harness.admin(f"slots/{THU_1500}/cancel", params={"deliver": "false"})
    harness.advance(minutes=5)
    result = await harness.say("Is everything good for Thursday?")
    assert "reply_blocked" in result["events"]
    assert "clinic_read" in result["events"]
    assert "confirmed" not in result["reply"].lower()
    assert "cancelled at the clinic" in result["reply"]
    assert "Here's the latest from the clinic." in result["reply"]
    blocked = harness.events("reply_blocked")[0]["payload"]
    assert "confirmed" in [word.lower() for word in blocked["words"]]


async def test_llm_that_keeps_lying_gets_fallback(make_harness):
    stubborn = {"Is everything good for Thursday?": {"extract": {"intent": "chat"}, "steps": [{"text": "It's confirmed."}, {"text": "Definitely booked."}]}}
    harness = await make_harness({**BOOK_THU, **stubborn})
    await harness.say("Book me Thursday 3pm with Dr A.")
    harness.advance(minutes=5)
    result = await harness.say("Is everything good for Thursday?")
    assert "Definitely booked" not in result["reply"] and "It's confirmed" not in result["reply"]
    assert "checking with the clinic" in result["reply"]
    assert harness.events("reply_blocked")[-1]["payload"]["reason"] == "regenerated_prose_still_unverified"
