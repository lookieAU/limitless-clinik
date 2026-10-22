import json

import httpx

from clinic.webhooks_out import sign
from demo.harness import SECRET
from tests.scenarios.scripts import BOOK_THU


def payload(event_id: str, version: int, status: str, booking: dict) -> dict:
    return {
        "event_id": event_id,
        "clinic_id": "clinic_a",
        "type": "booking.cancelled" if status == "cancelled" else "booking.rescheduled",
        "occurred_utc": "2026-11-02T04:00:00Z",
        "booking": {**booking, "status": status, "version": version},
    }


async def post(client: httpx.AsyncClient, body: dict, secret: str = SECRET) -> httpx.Response:
    raw = json.dumps(body).encode()
    return await client.post("/webhooks/clinic", content=raw, headers={"X-Signature": sign(secret, raw)})


async def booked(harness) -> dict:
    await harness.say("Book me Thursday 3pm with Dr A.")
    return (await harness.clinic.get("/clinics/clinic_a/bookings/bk_0003", headers={"X-Api-Key": "harness-clinic-key"})).json()


async def test_out_of_order_and_duplicate_events(make_harness):
    harness = await make_harness(BOOK_THU)
    booking = await booked(harness)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=harness.agent_app), base_url="http://agent")
    assert (await post(client, payload("e3", 3, "cancelled", booking))).json()["status"] == "booking_cancelled"
    assert (await post(client, payload("e2", 2, "confirmed", booking))).json()["status"] == "applied"
    assert (await post(client, payload("e3", 3, "cancelled", booking))).json()["status"] == "duplicate"
    row = harness.agent_ctx.conn.execute("SELECT status, version, source FROM verified_state WHERE booking_id = 'bk_0003'").fetchone()
    assert tuple(row) == ("cancelled", 3, "webhook")
    notices = harness.agent_ctx.conn.execute("SELECT count(*) FROM pending_notices").fetchone()[0]
    assert notices == 1
    await client.aclose()


async def test_bad_signature_rejected(make_harness):
    harness = await make_harness(BOOK_THU)
    booking = await booked(harness)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=harness.agent_app), base_url="http://agent")
    response = await post(client, payload("e9", 9, "cancelled", booking), secret="wrong")
    assert response.status_code == 401
    assert harness.events("webhook_rejected")
    await client.aclose()
