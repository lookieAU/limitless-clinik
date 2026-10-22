from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from agent.app import create_app as create_agent_app
from agent.context import AgentContext, build_context as build_agent_context
from agent.llm.scripted import ScriptedProvider
from agent.llm.types import LLMProvider
from agent.memory.embedder import HashEmbedder
from agent.repo.audit import events_of_type
from agent.settings import AgentSettings
from clinic.app import create_app as create_clinic_app
from clinic.context import ClinicContext, build_context as build_clinic_context
from clinic.settings import ClinicSettings
from shared.clock import FixedClock
from shared.sqlite import many
from shared.time import parse_utc

DEMO_NOW = parse_utc("2026-11-02T03:30:00Z")
API_KEY = "harness-clinic-key"
SECRET = "harness-webhook-secret"


@dataclass
class Harness:
    clock: FixedClock
    clinic_ctx: ClinicContext
    agent_ctx: AgentContext
    clinic: httpx.AsyncClient
    agent_app: object
    llm: LLMProvider
    clients: dict[str, httpx.AsyncClient] = field(default_factory=dict)

    async def login(self, user_id: str = "u_asha") -> httpx.AsyncClient:
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.agent_app), base_url="http://agent")
        code = (await client.post("/api/login/code", json={"user_id": user_id})).json()["code"]
        response = await client.post("/api/login", json={"user_id": user_id, "code": code})
        response.raise_for_status()
        self.clients[user_id] = client
        return client

    async def new_session(self, user_id: str = "u_asha") -> None:
        client = self.clients.get(user_id) or await self.login(user_id)
        (await client.post("/api/session/new")).raise_for_status()

    async def say(self, text: str, user_id: str = "u_asha", client_msg_id: str | None = None) -> dict:
        client = self.clients.get(user_id) or await self.login(user_id)
        response = await client.post("/api/chat", json={"text": text, "client_msg_id": client_msg_id})
        response.raise_for_status()
        return response.json()

    async def state(self, user_id: str = "u_asha") -> dict:
        client = self.clients.get(user_id) or await self.login(user_id)
        return (await client.get("/api/state")).json()

    async def admin(self, path: str, json: dict | None = None, params: dict | None = None) -> dict:
        response = await self.clinic.post(f"/admin/{path}", json=json, params=params)
        response.raise_for_status()
        return response.json()

    def advance(self, **delta) -> None:
        self.clock.advance(timedelta(**delta))

    def clinic_bookings(self, customer_id: str = "c_asha") -> list[dict]:
        return many(self.clinic_ctx.conn, "SELECT * FROM bookings WHERE customer_id = ? ORDER BY id", (customer_id,))

    def clinic_writes(self) -> int:
        return len(many(self.clinic_ctx.conn, "SELECT key FROM idempotency_keys"))

    def events(self, event_type: str) -> list[dict]:
        return events_of_type(self.agent_ctx.conn, event_type)

    async def close(self) -> None:
        for client in self.clients.values():
            await client.aclose()
        await self.clinic.aclose()


async def build_harness(
    directory: Path,
    script: dict | None = None,
    enabled: tuple[str, ...] = ("clinic_a",),
    llm: LLMProvider | None = None,
    now: datetime = DEMO_NOW,
    clinic_timeout_s: float = 0.2,
    hang_seconds: float = 0.6,
) -> Harness:
    clock = FixedClock(now)
    clinic_settings = ClinicSettings(
        db_path=str(directory / "clinic.db"),
        api_key=API_KEY,
        webhook_secret=SECRET,
        agent_webhook_url="http://agent/webhooks/clinic",
        hang_seconds=hang_seconds,
        slow_seconds=0.01,
        webhook_backoff=(0.0, 0.0),
    )
    clinic_ctx = build_clinic_context(clinic_settings, clock, httpx.AsyncClient())
    clinic_app = create_clinic_app(clinic_ctx)
    agent_settings = AgentSettings(
        db_path=str(directory / "agent.db"),
        clinic_api_key=API_KEY,
        webhook_secret=SECRET,
        session_secret="harness-session-secret",
        enabled_clinics=enabled,
        clinic_timeout_s=clinic_timeout_s,
        background_tasks=False,
    )
    clinic_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=clinic_app), base_url="http://clinic")
    provider = llm or ScriptedProvider(script or {})
    agent_ctx = build_agent_context(agent_settings, clock, clinic_client, provider, HashEmbedder())
    agent_app = create_agent_app(agent_ctx)
    clinic_ctx.webhooks.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=agent_app))
    admin_client = httpx.AsyncClient(transport=httpx.ASGITransport(app=clinic_app), base_url="http://clinic")
    return Harness(clock, clinic_ctx, agent_ctx, admin_client, agent_app, provider)
