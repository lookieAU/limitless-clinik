import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from agent.bus import Bus
from agent.clinic.registry import Registry, build_registry
from agent.llm.scripted import ScriptedProvider
from agent.llm.types import LLMProvider
from agent.memory.embedder import Embedder, build_embedder
from agent.repo.users import seed_users
from agent.settings import AgentSettings
from shared.clock import Clock, clock_from_env
from shared.sqlite import connect, migrate

MIGRATIONS = Path(__file__).parent / "migrations"
log = logging.getLogger("agent")


@dataclass
class AgentContext:
    settings: AgentSettings
    conn: sqlite3.Connection
    clock: Clock
    registry: Registry
    llm: LLMProvider
    embedder: Embedder
    bus: Bus
    http: httpx.AsyncClient
    calendar_sync: object | None = None
    doctor_cache: dict = field(default_factory=dict)

    async def doctor_names(self) -> dict[str, str]:
        key = tuple(self.registry.enabled_ids)
        if key not in self.doctor_cache:
            names = {}
            for adapter in self.registry.enabled():
                names.update({doctor["id"]: doctor["name"] for doctor in await adapter.doctors()})
            self.doctor_cache[key] = names
        return self.doctor_cache[key]


def build_llm(settings: AgentSettings) -> LLMProvider:
    if settings.llm_provider == "anthropic":
        if settings.anthropic_api_key:
            from agent.llm.anthropic_provider import AnthropicProvider

            return AnthropicProvider(settings.anthropic_api_key, settings.anthropic_model)
        log.warning("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is empty; using the scripted provider")
    return ScriptedProvider()


def build_context(
    settings: AgentSettings | None = None,
    clock: Clock | None = None,
    clinic_client: httpx.AsyncClient | None = None,
    llm: LLMProvider | None = None,
    embedder: Embedder | None = None,
) -> AgentContext:
    settings = settings or AgentSettings.from_env()
    clock = clock or clock_from_env()
    conn = connect(settings.db_path)
    migrate(conn, MIGRATIONS)
    seed_users(conn, clock.now())
    http = clinic_client or httpx.AsyncClient(base_url=settings.clinic_base_url, timeout=settings.clinic_timeout_s + 2)
    registry = build_registry(http, settings.clinic_api_key, settings.clinic_timeout_s, settings.enabled_clinics)
    return AgentContext(
        settings=settings,
        conn=conn,
        clock=clock,
        registry=registry,
        llm=llm or build_llm(settings),
        embedder=embedder or build_embedder(settings.embedder, settings.model_cache),
        bus=Bus(),
        http=http,
    )
