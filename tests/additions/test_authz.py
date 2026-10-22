from tests.scenarios.scripts import call, claim


def cancel_script(ref: str) -> dict:
    text = f"Cancel booking {ref}"
    return {text: {"extract": {"intent": "cancel", "claims": [claim("booking_ref", ref, ref)]}, "steps": [call("cancel", booking_ref=ref), {"text": "Let me know if I can help further."}]}}


async def test_cannot_cancel_another_customers_booking(make_harness):
    harness = await make_harness({**cancel_script("CA-1001"), **cancel_script("CA-9999")})
    other = harness.clinic_bookings("c_walkin")
    writes = harness.clinic_writes()
    existing = await harness.say("Cancel booking CA-1001")
    missing = await harness.say("Cancel booking CA-9999")
    assert harness.clinic_writes() == writes
    assert harness.clinic_bookings("c_walkin") == other
    assert len(harness.events("authz_denied")) == 2
    assert existing["reply"] == missing["reply"]
    assert "couldn't find that booking on your account" in existing["reply"]
