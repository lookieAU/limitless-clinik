from icalendar import Calendar

from agent.repo import users
from tests.scenarios.scripts import BOOK_THU, THU_1500


async def feed(harness) -> Calendar:
    token = users.get_user(harness.agent_ctx.conn, "u_asha")["ics_token"]
    client = harness.clients["u_asha"]
    response = await client.get(f"/calendar/{token}.ics")
    assert response.headers["content-type"].startswith("text/calendar")
    return Calendar.from_ical(response.content)


async def test_feed_tracks_verified_state_only(make_harness):
    harness = await make_harness(BOOK_THU)
    await harness.say("Book me Thursday 3pm with Dr A.")
    events = list((await feed(harness)).walk("VEVENT"))
    assert len(events) == 1
    assert str(events[0]["status"]) == "CONFIRMED"
    assert str(events[0]["uid"]) == "bk_0003@booking-agent"
    assert events[0]["dtstart"].dt.isoformat() == "2026-11-05T09:30:00+00:00"
    assert "observed" in str(events[0]["x-source"])
    await harness.admin(f"slots/{THU_1500}/cancel")
    cancelled = list((await feed(harness)).walk("VEVENT"))
    assert str(cancelled[0]["status"]) == "CANCELLED"
    assert int(cancelled[0]["sequence"]) == 2


async def test_claims_never_appear_in_feed(make_harness):
    script = {"I'd prefer Thursday at 3pm with Dr A.": {"extract": {"intent": "chat", "claims": [
        {"subject": "day", "value": "thu", "raw_span": "Thursday"}, {"subject": "time_window", "value": "15:00", "raw_span": "3pm"}]}}}
    harness = await make_harness(script)
    await harness.say("I'd prefer Thursday at 3pm with Dr A.")
    assert list((await feed(harness)).walk("VEVENT")) == []


async def test_unknown_token_is_404(make_harness):
    harness = await make_harness()
    client = await harness.login()
    assert (await client.get("/calendar/nope.ics")).status_code == 404
