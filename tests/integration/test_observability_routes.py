import pytest
from quart import Quart

from daralla_backend.web.app_quart import create_quart_app


@pytest.fixture
def quart_app_plain():
    return create_quart_app()


@pytest.mark.asyncio
async def test_request_id_is_added_to_response_headers(quart_app_plain: Quart):
    client = quart_app_plain.test_client()
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID")


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_counters(quart_app_plain: Quart):
    client = quart_app_plain.test_client()
    await client.get("/health")
    response = await client.get("/metrics")
    assert response.status_code == 200
    data = await response.get_json()
    assert "metrics" in data
    assert any(key.startswith("http_requests_total|") for key in data["metrics"].keys())


@pytest.mark.asyncio
async def test_ready_endpoint_returns_ok_or_degraded(quart_app_plain: Quart):
    client = quart_app_plain.test_client()
    response = await client.get("/ready")
    assert response.status_code in (200, 503)
    data = await response.get_json()
    assert "status" in data
    assert "checks" in data
