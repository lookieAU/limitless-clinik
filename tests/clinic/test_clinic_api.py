import asyncio
import hashlib
import hmac
import json

import pytest

from shared.sqlite import many

THU_1500 = "dr_a_20261105_1500"
FRI_1100 = "dr_a_20261106_1100"
FRI_0900 = "dr_a_20261106_0900"
BASE = "/clinics/clinic_a"


async def book(client, key, slot=THU_1500, customer="c_asha"):
    return await client.post(
        f"{BASE}/bookings", json={"customer_id": customer, "slot_id": slot}, headers={"Idempotency-Key": key}
    )


def booking_count(ctx, customer="c_asha"):
    return len(many(ctx.conn, "SELECT id FROM bookings WHERE customer_id = ?", (customer,)))


async def test_seed_has_three_doctors_and_fixture_slots(clinic_http):
    doctors = (await clinic_http.get(f"{BASE}/doctors")).json()["doctors"]
    assert [d["id"] for d in doctors] == ["dr_a", "dr_b", "dr_c"]
    friday = await clinic_http.get(
        f"{BASE}/slots", params={"doctor_id": "dr_a", "from": "2026-11-06T03:30:00Z", "to": "2026-11-06T06:30:00Z"}
    )
    ids = [slot["id"] for slot in friday.json()["slots"]]
    assert FRI_0900 in ids and FRI_1100 not in ids


async def test_seed_records_rejected_conflicting_staff_edit(clinic_ctx):
    events = many(clinic_ctx.conn, "SELECT type, origin FROM events WHERE type = 'booking.rescheduled'")
    assert events == [{"type": "booking.rescheduled", "origin": "clinic"}]


async def test_api_key_required(clinic_http):
    response = await clinic_http.get(f"{BASE}/doctors", headers={"X-Api-Key": "wrong"})
    assert response.status_code == 401


async def test_same_key_replays_first_response(clinic_ctx, clinic_http):
    first, second = await book(clinic_http, "k1"), await book(clinic_http, "k1")
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert booking_count(clinic_ctx) == 1


async def test_key_reuse_with_different_request_conflicts(clinic_http):
    await book(clinic_http, "k1")
    response = await book(clinic_http, "k1", slot=FRI_0900)
    assert response.status_code == 409 and response.json()["error"] == "idempotency_conflict"


async def test_full_slot_rejected(clinic_http):
    response = await book(clinic_http, "k2", slot=FRI_1100)
    assert response.status_code == 409 and response.json()["error"] == "slot_unavailable"


async def test_stale_version_reschedule_gets_412(clinic_http):
    booking = (await book(clinic_http, "k1")).json()
    headers = {"Idempotency-Key": "m1", "If-Match": str(booking["version"] + 5)}
    response = await clinic_http.patch(f"{BASE}/bookings/{booking['booking_id']}", json={"slot_id": FRI_0900}, headers=headers)
    assert response.status_code == 412


async def test_reschedule_in_place_bumps_version(clinic_http):
    booking = (await book(clinic_http, "k1")).json()
    headers = {"Idempotency-Key": "m1", "If-Match": str(booking["version"])}
    moved = await clinic_http.patch(f"{BASE}/bookings/{booking['booking_id']}", json={"slot_id": FRI_0900}, headers=headers)
    assert moved.json()["slot"]["id"] == FRI_0900 and moved.json()["version"] == booking["version"] + 1


async def test_timeout_after_commit_leaves_exactly_one_booking(clinic_ctx, clinic_http):
    await clinic_http.post("/admin/faults", json={"endpoint": "book", "mode": "timeout_after_commit"})
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.1):
            await book(clinic_http, "k-after")
    found = (await clinic_http.get(f"{BASE}/bookings", params={"idempotency_key": "k-after"})).json()["bookings"]
    assert len(found) == 1 and found[0]["status"] == "confirmed"
    retry = await book(clinic_http, "k-after")
    assert retry.json()["booking_id"] == found[0]["booking_id"]
    assert booking_count(clinic_ctx) == 1


async def test_timeout_before_commit_writes_nothing(clinic_ctx, clinic_http):
    await clinic_http.post("/admin/faults", json={"endpoint": "book", "mode": "timeout_before_commit"})
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.1):
            await book(clinic_http, "k-before")
    assert (await clinic_http.get(f"{BASE}/bookings", params={"idempotency_key": "k-before"})).json()["bookings"] == []
    assert (await book(clinic_http, "k-before")).status_code == 201
    assert booking_count(clinic_ctx) == 1


async def test_admin_slot_cancel_sends_signed_webhook(clinic_http, received_webhooks):
    booking = (await book(clinic_http, "k1")).json()
    result = (await clinic_http.post(f"/admin/slots/{THU_1500}/cancel")).json()
    assert result["cancelled"][0]["status"] == "cancelled"
    request = received_webhooks[0]
    expected = hmac.new(b"test-secret", request.content, hashlib.sha256).hexdigest()
    assert request.headers["X-Signature"] == expected
    payload = json.loads(request.content)
    assert payload["type"] == "booking.cancelled"
    assert payload["booking"]["booking_id"] == booking["booking_id"]
    assert payload["booking"]["version"] == booking["version"] + 1


async def test_clinic_b_dialect(clinic_http, received_webhooks):
    base = "/clinics/clinic_b"
    created = await clinic_http.post(
        f"{base}/bookings", json={"customer_id": "c_asha", "slot_id": "dr_f_20261102_1500"}, headers={"Idempotency-Key": "b1"}
    )
    booking = created.json()
    assert booking["ref"].startswith("CB-")
    patch = await clinic_http.patch(
        f"{base}/bookings/{booking['booking_id']}", json={"slot_id": "dr_f_20261103_1500"},
        headers={"Idempotency-Key": "b2", "If-Match": "1"},
    )
    assert patch.status_code == 405
    cutoff = await clinic_http.delete(f"{base}/bookings/{booking['booking_id']}", headers={"Idempotency-Key": "b3"})
    assert cutoff.status_code == 409 and cutoff.json()["error"] == "cancel_cutoff"
    await clinic_http.post(f"/admin/bookings/{booking['booking_id']}/cancel")
    assert received_webhooks == []
    events = (await clinic_http.get(f"{base}/events", params={"since": 0})).json()["events"]
    assert [e["type"] for e in events] == ["appointment.created", "appointment.voided"]
    assert events[-1]["booking"]["status"] == "cancelled_by_clinic"
