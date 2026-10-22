import sqlite3
from dataclasses import dataclass
from pathlib import Path

import httpx

from clinic.seed import seed
from clinic.settings import ClinicSettings
from clinic.webhooks_out import WebhookSender
from shared.clock import Clock, clock_from_env
from shared.sqlite import connect, migrate

MIGRATIONS = Path(__file__).parent / "migrations"


@dataclass
class ClinicContext:
    settings: ClinicSettings
    conn: sqlite3.Connection
    clock: Clock
    webhooks: WebhookSender


def build_context(
    settings: ClinicSettings | None = None,
    clock: Clock | None = None,
    webhook_client: httpx.AsyncClient | None = None,
) -> ClinicContext:
    settings = settings or ClinicSettings.from_env()
    clock = clock or clock_from_env()
    conn = connect(settings.db_path)
    migrate(conn, MIGRATIONS)
    seed(conn, clock)
    sender = WebhookSender(
        conn,
        webhook_client or httpx.AsyncClient(timeout=5.0),
        settings.agent_webhook_url,
        settings.webhook_secret,
        clock,
        settings.webhook_backoff,
    )
    return ClinicContext(settings, conn, clock, sender)
