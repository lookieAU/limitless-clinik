import httpx
import pytest

from clinic.app import create_app as create_clinic_app
from clinic.context import build_context
from clinic.settings import ClinicSettings
from shared.clock import FixedClock
from shared.time import parse_utc

DEMO_NOW = parse_utc("2026-11-02T03:30:00Z")
API_KEY = "test-clinic-key"


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(DEMO_NOW)


@pytest.fixture
def received_webhooks() -> list[httpx.Request]:
    return []


@pytest.fixture
def clinic_ctx(tmp_path, clock, received_webhooks):
    def capture(request: httpx.Request) -> httpx.Response:
        received_webhooks.append(request)
        return httpx.Response(200, json={"ok": True})

    settings = ClinicSettings(
        db_path=str(tmp_path / "clinic.db"),
        api_key=API_KEY,
        webhook_secret="test-secret",
        agent_webhook_url="http://agent/webhooks/clinic",
        hang_seconds=0.5,
        slow_seconds=0.01,
        webhook_backoff=(0.0, 0.0),
    )
    webhook_client = httpx.AsyncClient(transport=httpx.MockTransport(capture))
    return build_context(settings, clock, webhook_client)


@pytest.fixture
async def clinic_http(clinic_ctx):
    transport = httpx.ASGITransport(app=create_clinic_app(clinic_ctx))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://clinic", headers={"X-Api-Key": API_KEY}
    ) as client:
        yield client
