import httpx

from agent.settings import AgentSettings
from demo.web import create_app as create_replay_app
from tests.scenarios.scripts import BOOK_THU

NOT_FRIDAY = {"Please, not Friday.": {"extract": {"intent": "chat", "claims": [{"subject": "day", "value": "fri", "polarity": "negative", "raw_span": "not Friday"}]}}}


async def browser(harness) -> httpx.AsyncClient:
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=harness.agent_app), base_url="http://agent")
    page = await client.post("/login/start", data={"user_id": "u_asha"})
    code = page.text.split('class="otp">')[1].split("<")[0]
    response = await client.post("/login/verify", data={"user_id": "u_asha", "code": code})
    assert response.status_code == 303 and response.headers["location"] == "/chat"
    return client


async def test_chat_reply_shows_chips_not_internals(make_harness):
    harness = await make_harness({**BOOK_THU, **NOT_FRIDAY})
    client = await browser(harness)
    page = (await client.get("/chat")).text
    assert "Hi Asha," in page and 'id="composer"' in page
    sent = (await client.post("/ui/send", data={"text": "Book me Thursday 3pm with Dr A.", "client_msg_id": "ui-1"})).text
    assert "confirmed by the clinic" in sent
    assert "CA-1003 · confirmed" in sent and 'chip success' in sent and 'chip secondary' in sent
    assert "Thursday" in sent and "<code>check_availability, book</code>" in sent
    assert "Provenance" not in sent and "Events:" not in sent
    panels = (await client.get("/ui/panels")).text
    assert "CA-1003" in panels and "Dr Arjun Mehta" in panels
    history = (await client.get("/chat")).text
    assert "CA-1003 · confirmed" in history
    await client.aclose()


async def test_switching_mode_starts_a_fresh_conversation(make_harness):
    harness = await make_harness(BOOK_THU)
    client = await browser(harness)
    await client.post("/ui/send", data={"text": "Book me Thursday 3pm with Dr A."})
    switched = await client.post("/session/new?mode=chat")
    assert switched.headers["location"] == "/chat?mode=chat"
    page = (await client.get("/chat")).text
    assert 'class="msg user"' not in page and "CA-1003" in page
    assert (await client.get("/ui/voice/token")).status_code == 404
    await client.aclose()


async def test_demo_controls_speak_plainly(make_harness):
    harness = await make_harness({**BOOK_THU, **NOT_FRIDAY})
    client = await browser(harness)
    await client.post("/ui/send", data={"text": "Book me Thursday 3pm with Dr A."})
    await client.post("/ui/send", data={"text": "Please, not Friday."})
    assert "Cancel, lose webhook" in (await client.get("/admin")).text
    rejected = (await client.post("/admin/act/summary", data={"lossy": "yes"})).text
    assert rejected.startswith("Rejected:") and "previous memory is kept" in rejected
    cancelled = (await client.post("/admin/act/cancel-slot", data={"ref": "CA-1003", "deliver": "true"})).text
    assert "sent a webhook" in cancelled
    activity = (await client.get("/admin/activity")).text
    assert "Nightly summary rejected" in activity and "Clinic changed booking CA-1003" in activity
    await client.aclose()


async def test_unauthenticated_chat_redirects(make_harness):
    harness = await make_harness()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=harness.agent_app), base_url="http://agent")
    assert (await client.get("/chat")).headers["location"] == "/login"
    assert (await client.post("/api/chat", json={"text": "hi"})).status_code == 401
    await client.aclose()


def test_voice_token_dispatches_the_clinik_agent():
    import jwt

    from agent.voice.token import voice_token

    settings = AgentSettings(livekit_url="wss://example.livekit.cloud", livekit_api_key="key", livekit_api_secret="s" * 32)
    issued = voice_token(settings, "u_asha", "ses_1")
    claims = jwt.decode(issued["token"], "s" * 32, algorithms=["HS256"])
    assert claims["sub"] == "u_asha" and claims["video"]["room"] == "clinik-ses_1"
    assert claims["roomConfig"]["agents"][0]["agentName"] == "clinik"


async def test_replay_web_steps_through_timeline():
    app = create_replay_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://replay") as client:
        assert "Start replay" in (await client.get("/replay")).text
        total = (await client.post("/replay/start")).json()["total"]
        for _ in range(total):
            data = (await client.post("/replay/next")).json()
        assert data["done"] and "Rejected" not in data["step"] and "summary REJECTED" in data["step"]
        await app.state.replay.harness.close()
        app.state.workdir.cleanup()
