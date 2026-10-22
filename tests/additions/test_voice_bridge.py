import httpx

from agent.voice.bridge import VoiceBridge, needs_confirmation
from tests.scenarios.scripts import BOOK_THU

NOT_FRIDAY = {"Not Friday please": {"extract": {"intent": "chat", "claims": [{"subject": "day", "value": "fri", "polarity": "negative", "raw_span": "Not Friday"}]}}}


async def bridge_for(harness) -> VoiceBridge:
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=harness.agent_app), base_url="http://agent")
    bridge = VoiceBridge(client, "u_asha")
    await bridge.login()
    return bridge


def test_low_confidence_negation_needs_confirmation():
    assert needs_confirmation("not Thursday", 0.6)
    assert needs_confirmation("गुरुवार नहीं", None)
    assert not needs_confirmation("not Thursday", 0.97)
    assert not needs_confirmation("Thursday works", 0.4)


async def test_negation_is_confirmed_before_reaching_the_agent(make_harness):
    harness = await make_harness(NOT_FRIDAY)
    bridge = await bridge_for(harness)
    ask = await bridge.respond("Not Friday please", confidence=0.5)
    assert "Is that right?" in ask.text and ask.filler is None
    assert harness.events("claims_extracted") == []
    await bridge.respond("yes")
    assert harness.events("claims_extracted")


async def test_booking_is_read_back_with_ref_and_goodbye_rechecks(make_harness):
    harness = await make_harness({**BOOK_THU, "Thanks, bye": {"extract": {"intent": "chat"}}})
    bridge = await bridge_for(harness)
    booked = await bridge.respond("Book me Thursday 3pm with Dr A.", confidence=0.95)
    assert "CA-1003" in booked.text and "Thu 5 Nov" in booked.text and booked.filler
    goodbye = await bridge.respond("Thanks, bye", confidence=0.95)
    assert "CA-1003" in goodbye.text and "Thu 5 Nov" in goodbye.text
    assert harness.events("status_recheck")
