from tests.scenarios.scripts import BOOK_THU


async def test_booking_reports_clinic_ref(make_harness):
    harness = await make_harness(BOOK_THU)
    result = await harness.say("Book me Thursday 3pm with Dr A.")
    bookings = harness.clinic_bookings()
    assert len(bookings) == 1
    ref = bookings[0]["ref"]
    assert ref in result["reply"]
    assert "confirmed by the clinic" in result["reply"]
    verified = [fact for fact in result["facts"] if fact["kind"] == "verified"]
    assert verified and verified[0]["source"] == "api" and ref in verified[0]["text"]
    claimed = [fact for fact in result["facts"] if fact["kind"] == "claimed"]
    assert any("Thursday" in fact["text"] for fact in claimed)
