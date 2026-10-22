import httpx
import pytest

from clinic.app import create_app as create_clinic


@pytest.mark.parametrize("service", ["clinic"])
async def test_health(clinic_ctx, service):
    transport = httpx.ASGITransport(app=create_clinic(clinic_ctx))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.json() == {"status": "ok", "service": service}
