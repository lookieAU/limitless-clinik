import json

import httpx

from agent.gcal import CalendarSync, event_id
from tests.scenarios.scripts import BOOK_THU, THU_1500


def fake_google(store: dict, calls: list):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "t"})
        body = json.loads(request.content) if request.content else {}
        if request.method == "PUT":
            if body["id"] not in store:
                return httpx.Response(404)
            store[body["id"]] = body
            return httpx.Response(200, json=body)
        store[body["id"]] = body
        return httpx.Response(200, json=body)

    return handler


async def test_verified_changes_sync_idempotently(make_harness):
    harness = await make_harness(BOOK_THU)
    store, calls = {}, []
    sync = CalendarSync(httpx.AsyncClient(transport=httpx.MockTransport(fake_google(store, calls))), "id", "secret", "refresh", "primary")
    harness.agent_ctx.calendar_sync = sync
    await harness.say("Book me Thursday 3pm with Dr A.")
    await sync.flush()
    key = event_id("bk_0003")
    assert store[key]["status"] == "confirmed" and "CA-1003" in store[key]["summary"]
    await harness.admin(f"slots/{THU_1500}/cancel")
    await sync.flush()
    assert store[key]["status"] == "cancelled" and len(store) == 1
    assert [method for method, path in calls if path != "/token"].count("POST") == 1


async def test_claims_never_reach_google(make_harness):
    script = {"I'd like Thursday at 3pm.": {"extract": {"intent": "chat", "claims": [{"subject": "day", "value": "thu", "raw_span": "Thursday"}]}}}
    harness = await make_harness(script)
    store, calls = {}, []
    sync = CalendarSync(httpx.AsyncClient(transport=httpx.MockTransport(fake_google(store, calls))), "id", "secret", "refresh", "primary")
    harness.agent_ctx.calendar_sync = sync
    await harness.say("I'd like Thursday at 3pm.")
    await sync.flush()
    assert store == {} and calls == []
