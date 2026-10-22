import os
from dataclasses import dataclass


def env_list(name: str, default: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in os.environ.get(name, default).split(",") if part.strip())


@dataclass(frozen=True)
class AgentSettings:
    db_path: str = "/data/agent.db"
    clinic_base_url: str = "http://clinic:8001"
    clinic_api_key: str = "dev-clinic-key"
    webhook_secret: str = "dev-webhook-secret"
    session_secret: str = "dev-session-secret"
    enabled_clinics: tuple[str, ...] = ("clinic_a",)
    llm_provider: str = "scripted"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: str = "medium"
    freshness_ttl_s: float = 120.0
    clinic_timeout_s: float = 3.0
    sync_gap_s: float = 600.0
    poll_interval_s: float = 15.0
    embedder: str = "hash"
    model_cache: str = "/data/models"
    background_tasks: bool = True

    @classmethod
    def from_env(cls) -> "AgentSettings":
        return cls(
            db_path=os.environ.get("AGENT_DB_PATH", cls.db_path),
            clinic_base_url=os.environ.get("CLINIC_BASE_URL", cls.clinic_base_url),
            clinic_api_key=os.environ.get("CLINIC_API_KEY", cls.clinic_api_key),
            webhook_secret=os.environ.get("WEBHOOK_SECRET", cls.webhook_secret),
            session_secret=os.environ.get("SESSION_SECRET", cls.session_secret),
            enabled_clinics=env_list("ENABLED_CLINICS", "clinic_a"),
            llm_provider=os.environ.get("LLM_PROVIDER", cls.llm_provider),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            anthropic_model=os.environ.get("ANTHROPIC_MODEL", cls.anthropic_model),
            anthropic_effort=os.environ.get("ANTHROPIC_EFFORT", cls.anthropic_effort),
            freshness_ttl_s=float(os.environ.get("FRESHNESS_TTL_S", cls.freshness_ttl_s)),
            clinic_timeout_s=float(os.environ.get("CLINIC_TIMEOUT_S", cls.clinic_timeout_s)),
            embedder=os.environ.get("EMBEDDER", cls.embedder),
            model_cache=os.environ.get("MODEL_CACHE", cls.model_cache),
        )
