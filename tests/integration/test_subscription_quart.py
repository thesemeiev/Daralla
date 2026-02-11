"""Integration tests for Quart subscription endpoint GET /sub/<token>."""
import pytest
from quart import Quart

from bot.web.app_quart import create_quart_app


@pytest.fixture
def quart_app():
    """Quart app without bot_app (only /health)."""
    return create_quart_app()


@pytest.mark.asyncio
async def test_subscription_unknown_token_returns_404(quart_app: Quart):
    """GET /sub/<unknown_token> returns 404 when route is not registered (no bot_app)."""
    client = quart_app.test_client()
    response = await client.get("/sub/unknown_token_12345")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_health_ok(quart_app: Quart):
    """GET /health returns 200 and status ok."""
    client = quart_app.test_client()
    response = await client.get("/health")
    assert response.status_code == 200
    data = await response.get_json()
    assert data.get("status") == "ok"
