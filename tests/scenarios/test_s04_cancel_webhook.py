from tests.scenarios.scripts import BOOK_THU, STATUS_QUESTION, THU_1500


async def test_next_contact_states_cancellation_first_and_offers_rebooking(make_harness):
    harness = await make_harness({**BOOK_THU, **STATUS_QUESTION, "Hi": {"extract": {"intent": "chat"}}})
    await harness.say("Book me Thursday 3pm with Dr A.")
    delivered = await harness.admin(f"slots/{THU_1500}/cancel")
    assert delivered["delivered"]
    harness.advance(days=1)
    await harness.new_session()
    result = await harness.say("Hi")
    first = result["reply"].split("\n\n")[0]
    assert first.startswith("First, an update from the clinic") and "cancelled by the clinic" in first
    assert "a webhook" in first
    assert "I can rebook you" in result["reply"] and "Nothing changes until you pick" in result["reply"]
    assert result["segments"][0]["kind"] == "notice"
    state = await harness.state()
    assert state["verified"][0]["status"] == "cancelled"
    overridden = [c for c in state["claims"] if c["status"] == "overridden"]
    assert {c["subject"] for c in overridden} >= {"day", "time_window"}
    offers = harness.agent_ctx.conn.execute("SELECT count(*) FROM pending_offers WHERE status = 'open'").fetchone()[0]
    assert offers >= 1
