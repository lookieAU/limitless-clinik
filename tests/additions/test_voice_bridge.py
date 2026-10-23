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
    assert "(" not in booked.text
    goodbye = await bridge.respond("Thanks, bye", confidence=0.95)
    assert "CA-1003" in goodbye.text and "Thu 5 Nov" in goodbye.text
    assert harness.events("status_recheck")


async def test_unknown_caller_falls_back_to_default_user(make_harness):
    harness = await make_harness()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=harness.agent_app), base_url="http://agent")
    bridge = VoiceBridge(client, "PA_random_identity")
    await bridge.login(fallback_user="u_ravi")
    assert bridge.user_id == "u_ravi"


async def test_spoken_turn_says_filler_then_the_agent_reply(make_harness):
    from agent.voice.bridge import handle_turn

    harness = await make_harness(BOOK_THU)
    bridge = await bridge_for(harness)
    spoken = []
    await handle_turn(bridge, lambda text, **kwargs: spoken.append(text), "Book me Thursday 3pm with Dr A.", 0.95, filler_after=0.0)
    assert spoken[0] == "Let me check." and "CA-1003" in spoken[1]
    assert "(" not in spoken[1] and "checked just now" not in spoken[1]


async def test_fast_reply_skips_the_filler(make_harness):
    from agent.voice.bridge import handle_turn

    harness = await make_harness(BOOK_THU)
    bridge = await bridge_for(harness)
    spoken = []
    await handle_turn(bridge, lambda text, **kwargs: spoken.append(text), "Book me Thursday 3pm with Dr A.", 0.95, filler_after=30.0)
    assert len(spoken) == 1 and "CA-1003" in spoken[0]


async def test_low_confidence_negation_is_asked_back_without_filler(make_harness):
    from agent.voice.bridge import handle_turn

    harness = await make_harness(NOT_FRIDAY)
    bridge = await bridge_for(harness)
    spoken = []
    await handle_turn(bridge, lambda text, **kwargs: spoken.append(text), "Not Friday please", 0.4)
    assert len(spoken) == 1 and "Is that right?" in spoken[0]
