import httpx

from demo.web import create_app as create_replay_app
from tests.scenarios.scripts import BOOK_THU


async def browser(harness) -> httpx.AsyncClient:
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=harness.agent_app), base_url="http://agent")
    page = await client.post("/login/start", data={"user_id": "u_asha"})
    code = page.text.split('class="otp">')[1].split("<")[0]
    response = await client.post("/login/verify", data={"user_id": "u_asha", "code": code})
    assert response.status_code == 303 and response.headers["location"] == "/chat"
    return client


NOT_FRIDAY = {"Please, not Friday.": {"extract": {"intent": "chat", "claims": [{"subject": "day", "value": "fri", "polarity": "negative", "raw_span": "not Friday"}]}}}


async def test_login_chat_panels_and_admin(make_harness):
    harness = await make_harness({**BOOK_THU, **NOT_FRIDAY})
    client = await browser(harness)
    assert "Asha Kulkarni" in (await client.get("/login")).text
    assert "Subscribe (.ics)" in (await client.get("/chat")).text
    sent = await client.post("/ui/send", data={"text": "Book me Thursday 3pm with Dr A.", "client_msg_id": "ui-1"})
    assert sent.headers["HX-Trigger"] == "panels"
    assert "confirmed by the clinic" in sent.text and "Provenance" in sent.text
    panels = (await client.get("/ui/panels")).text
    assert "CA-1003" in panels and "Thursday" in panels
    assert "Clinic cancels slot" in (await client.get("/admin")).text
    await client.post("/ui/send", data={"text": "Please, not Friday."})
    summary = await client.post("/admin/act/summary", data={"lossy": "yes"})
    assert "REJECTED" in summary.text
    assert (await client.get("/static/htmx.min.js")).status_code == 200
    await client.aclose()


async def test_unauthenticated_chat_redirects(make_harness):
    harness = await make_harness()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=harness.agent_app), base_url="http://agent")
    assert (await client.get("/chat")).headers["location"] == "/login"
    assert (await client.post("/api/chat", json={"text": "hi"})).status_code == 401
    await client.aclose()


async def test_replay_web_steps_through_timeline():
    app = create_replay_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://replay") as client:
        assert "Start replay" in (await client.get("/replay")).text
        assert "Step 1 of" in (await client.post("/replay/start")).text
        last = None
        for _ in range(9):
            last = await client.post("/replay/next")
            assert last.status_code == 200
        assert "Replay finished" in last.text and "summary REJECTED" in last.text
        await app.state.replay.harness.close()
        app.state.workdir.cleanup()
