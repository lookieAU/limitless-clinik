from tests.scenarios.scripts import BOOK_THU


async def test_timeout_before_commit_reconciles_then_retries_same_key(make_harness):
    harness = await make_harness(BOOK_THU)
    await harness.admin("faults", json={"endpoint": "book", "mode": "timeout_before_commit"})
    result = await harness.say("Book me Thursday 3pm with Dr A.")
    bookings = harness.clinic_bookings()
    assert len(bookings) == 1
    assert "I'm not sure that went through" in result["reply"]
    assert "retried the same request" in result["reply"]
    assert bookings[0]["ref"] in result["reply"]
    assert [e["payload"]["found"] for e in harness.events("reconciled")] == [False]
    rows = harness.agent_ctx.conn.execute("SELECT state FROM outbox").fetchall()
    assert [row["state"] for row in rows] == ["succeeded"]


async def test_timeout_after_commit_finds_booking_without_retry(make_harness):
    harness = await make_harness(BOOK_THU)
    await harness.admin("faults", json={"endpoint": "book", "mode": "timeout_after_commit"})
    result = await harness.say("Book me Thursday 3pm with Dr A.")
    bookings = harness.clinic_bookings()
    assert len(bookings) == 1
    assert "I'm not sure that went through" in result["reply"]
    assert "did record it, so I didn't send it again" in result["reply"]
    assert "retried" not in result["reply"]
    assert bookings[0]["ref"] in result["reply"]
    assert [e["payload"]["found"] for e in harness.events("reconciled")] == [True]
