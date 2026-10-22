import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ClinicSettings:
    db_path: str = "/data/clinic.db"
    api_key: str = "dev-clinic-key"
    webhook_secret: str = "dev-webhook-secret"
    agent_webhook_url: str = "http://agent:8000/webhooks/clinic"
    hang_seconds: float = 10.0
    slow_seconds: float = 1.5
    webhook_backoff: tuple[float, ...] = (0.2, 0.5, 1.0)

    @classmethod
    def from_env(cls) -> "ClinicSettings":
        return cls(
            db_path=os.environ.get("CLINIC_DB_PATH", cls.db_path),
            api_key=os.environ.get("CLINIC_API_KEY", cls.api_key),
            webhook_secret=os.environ.get("WEBHOOK_SECRET", cls.webhook_secret),
            agent_webhook_url=os.environ.get("AGENT_WEBHOOK_URL", cls.agent_webhook_url),
            hang_seconds=float(os.environ.get("FAULT_HANG_SECONDS", cls.hang_seconds)),
        )
