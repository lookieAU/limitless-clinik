import httpx
import pytest

from agent.app import create_app as create_agent
from clinic.app import create_app as create_clinic


@pytest.mark.parametrize(("factory", "service"), [(create_clinic, "clinic"), (create_agent, "agent")])
async def test_health(factory, service):
    transport = httpx.ASGITransport(app=factory())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.json() == {"status": "ok", "service": service}
