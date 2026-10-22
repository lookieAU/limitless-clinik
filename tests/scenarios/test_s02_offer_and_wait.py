from tests.scenarios.scripts import BOOK_THU, FRI_0900, MOVE_FRI


async def test_full_slot_offers_alternative_and_waits(make_harness):
    harness = await make_harness({**BOOK_THU, **MOVE_FRI})
    await harness.say("Book me Thursday 3pm with Dr A.")
    writes_before = harness.clinic_writes()
    result = await harness.say("Actually make it Friday before noon.")
    assert harness.clinic_writes() == writes_before
    assert "9:00 am" in result["reply"] and "Nothing changes until you say yes" in result["reply"]
    assert harness.clinic_bookings()[0]["slot_id"] == "dr_a_20261105_1500"
    refusals = harness.events("gate_refused")
    assert refusals and refusals[-1]["payload"]["code"] == "consent_required"
    offers = harness.agent_ctx.conn.execute("SELECT slot_id, status FROM pending_offers").fetchall()
    assert [tuple(row) for row in offers] == [(FRI_0900, "open")]


async def test_booking_happens_only_after_yes(make_harness):
    harness = await make_harness({**BOOK_THU, **MOVE_FRI})
    await harness.say("Book me Thursday 3pm with Dr A.")
    await harness.say("Actually make it Friday before noon.")
    result = await harness.say("Yes")
    booking = harness.clinic_bookings()[0]
    assert booking["slot_id"] == FRI_0900 and booking["version"] == 2
    assert "Fri 6 Nov, 9:00 am IST is confirmed by the clinic" in result["reply"]
