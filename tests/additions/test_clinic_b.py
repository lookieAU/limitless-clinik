import pytest

from tests.scenarios.scripts import call, claim

CLINICS = {
    "clinic_a": {"doctor": "dr_a", "name": "Dr A", "slot": "dr_a_20261105_1500", "source": "a webhook"},
    "clinic_b": {"doctor": "dr_f", "name": "Dr F", "slot": "dr_f_20261105_1500", "source": "their status feed"},
}


def script(clinic: str) -> dict:
    info = CLINICS[clinic]
    text = f"Book me Thursday 3pm with {info['name']}."
    return {
        text: {
            "extract": {"intent": "book", "claims": [claim("day", "thu", "Thursday"), claim("time_window", "15:00", "3pm"), claim("doctor", info["doctor"], info["name"])]},
            "steps": [call("check_availability", clinic_id=clinic, doctor_id=info["doctor"], date_from="2026-11-05"), call("book", slot_id=info["slot"])],
        },
        "Hi": {"extract": {"intent": "chat"}},
        "Did you confirm it?": {"extract": {"intent": "status_query"}},
        "Cancel it please.": {"extract": {"intent": "cancel"}, "steps": [call("cancel")]},
    }


async def booked(make_harness, clinic: str):
    harness = await make_harness(script(clinic), enabled=(clinic,))
    await harness.say(f"Book me Thursday 3pm with {CLINICS[clinic]['name']}.")
    assert len(harness.clinic_bookings()) == 1
    return harness


@pytest.mark.parametrize("clinic", CLINICS)
async def test_cancellation_reaches_customer_first(make_harness, clinic):
    harness = await booked(make_harness, clinic)
    await harness.admin(f"slots/{CLINICS[clinic]['slot']}/cancel")
    harness.advance(days=1)
    await harness.new_session()
    result = await harness.say("Hi")
    first = result["reply"].split("\n\n")[0]
    assert first.startswith("First, an update from the clinic") and CLINICS[clinic]["source"] in first


@pytest.mark.parametrize("clinic", CLINICS)
async def test_did_you_confirm_after_cancellation(make_harness, clinic):
    harness = await booked(make_harness, clinic)
    await harness.admin(f"slots/{CLINICS[clinic]['slot']}/cancel")
    result = await harness.say("Did you confirm it?")
    assert "clinic_read" in result["events"]
    assert "confirmed" not in result["reply"].lower() and "cancelled at the clinic" in result["reply"]


async def test_clinic_b_cutoff_refuses_without_clinic_call(make_harness):
    harness = await make_harness(script("clinic_b"), enabled=("clinic_b",))
    harness.advance(days=2, hours=12)
    await harness.say("Book me Thursday 3pm with Dr F.")
    writes = harness.clinic_writes()
    result = await harness.say("Cancel it please.")
    assert harness.clinic_writes() == writes
    assert "24 hours' notice" in result["reply"]
    assert harness.events("gate_refused")[-1]["payload"]["code"] == "cancel_cutoff"


async def test_clinic_b_customer_cancel_is_voided_and_normalized(make_harness):
    harness = await booked(make_harness, "clinic_b")
    result = await harness.say("Cancel it please.")
    raw = (await harness.clinic.get("/clinics/clinic_b/bookings/bk_0003", headers={"X-Api-Key": "harness-clinic-key"})).json()
    assert raw["status"] == "voided"
    assert "Cancelled at the clinic" in result["reply"]
    state = await harness.state()
    assert state["verified"][0]["status"] == "cancelled"
