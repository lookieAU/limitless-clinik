from tests.scenarios.scripts import BOOK_THU


async def test_singapore_customer_books_in_clinic_time(make_harness):
    harness = await make_harness(BOOK_THU)
    result = await harness.say("Book me Thursday 3pm with Dr A.", user_id="u_mei")
    booking = harness.clinic_bookings("c_mei")[0]
    assert booking["slot_id"] == "dr_a_20261105_1500"
    slot = harness.clinic_ctx.conn.execute("SELECT start_utc FROM slots WHERE id = ?", (booking["slot_id"],)).fetchone()
    assert slot["start_utc"] == "2026-11-05T09:30:00Z"
    assert "Thu 5 Nov, 3:00 pm IST (5:30 pm SGT)" in result["reply"]


async def test_stored_timestamps_are_utc(make_harness):
    harness = await make_harness(BOOK_THU)
    await harness.say("Book me Thursday 3pm with Dr A.")
    conn = harness.agent_ctx.conn
    stamps = [row[0] for row in conn.execute("SELECT observed_utc FROM verified_state UNION ALL SELECT created_utc FROM claims")]
    assert stamps and all(stamp.endswith("Z") for stamp in stamps)
