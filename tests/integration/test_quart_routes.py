"""Integration tests for Quart routes: /api/prices, /api/auth/register, /webhook/yookassa, /api/admin/check."""
import pytest
from unittest.mock import patch
from quart import Quart

from bot.web.app_quart import create_quart_app
from bot.web.routes.payment import parse_yookassa_webhook_payload


@pytest.fixture
def quart_app_with_routes():
    """Quart app with all blueprints registered (mock bot_app)."""
    return create_quart_app(bot_app=object())


@pytest.mark.asyncio
async def test_get_api_prices_returns_200_and_prices(quart_app_with_routes: Quart):
    """GET /api/prices returns 200 and contains prices."""
    client = quart_app_with_routes.test_client()
    response = await client.get("/api/prices")
    assert response.status_code == 200
    data = await response.get_json()
    assert data.get("success") is True
    assert "prices" in data
    assert "month" in data
    assert "3month" in data


@pytest.mark.asyncio
async def test_post_webhook_yookassa_invalid_body_returns_400(quart_app_with_routes: Quart):
    """POST /webhook/yookassa with missing 'object' returns 400."""
    client = quart_app_with_routes.test_client()
    response = await client.post(
        "/webhook/yookassa",
        json={"event": "payment.succeeded"},
    )
    assert response.status_code == 400
    data = await response.get_json()
    assert data.get("status") == "error"


def test_parse_yookassa_refund_succeeded_maps_to_payment_id_and_refunded():
    """refund.succeeded: ищем платёж по payment_id, статус для БД — refunded."""
    r = parse_yookassa_webhook_payload(
        {
            "event": "refund.succeeded",
            "object": {
                "id": "2f9e4b2a-000f-5000-9000-1b2c3d4e5f6a",
                "payment_id": "2f9e4b2a-000f-5000-8000-1b2c3d4e5f60",
                "status": "succeeded",
            },
        }
    )
    assert r == ("2f9e4b2a-000f-5000-8000-1b2c3d4e5f60", "refunded")


def test_parse_yookassa_payment_succeeded_unchanged():
    r = parse_yookassa_webhook_payload(
        {
            "event": "payment.succeeded",
            "object": {"id": "pay-uuid", "status": "succeeded"},
        }
    )
    assert r == ("pay-uuid", "succeeded")


def test_parse_yookassa_legacy_no_event_still_payment():
    """Старые/минимальные payload без event обрабатываем как платёж."""
    r = parse_yookassa_webhook_payload({"object": {"id": "p1", "status": "pending"}})
    assert r == ("p1", "pending")


def test_parse_yookassa_unknown_event_skips_processing():
    assert (
        parse_yookassa_webhook_payload({"event": "deal.closed", "object": {"id": "x"}}) is None
    )


def test_parse_yookassa_refund_succeeded_missing_payment_id_raises():
    with pytest.raises(ValueError):
        parse_yookassa_webhook_payload(
            {"event": "refund.succeeded", "object": {"id": "r1", "status": "succeeded"}}
        )


@pytest.mark.asyncio
async def test_post_webhook_yookassa_empty_object_returns_400(quart_app_with_routes: Quart):
    """POST /webhook/yookassa with object missing id/status returns 400."""
    client = quart_app_with_routes.test_client()
    response = await client.post(
        "/webhook/yookassa",
        json={"object": {}},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_post_api_auth_register_success(quart_app_with_routes: Quart, db):
    """POST /api/auth/register with valid username/password returns 200 and token."""
    # db fixture ensures init_all_db() has run (test DB from conftest)
    client = quart_app_with_routes.test_client()
    response = await client.post(
        "/api/auth/register",
        json={"username": "testuser123", "password": "password123"},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data.get("success") is True
    assert "token" in data
    assert "user_id" in data


@pytest.mark.asyncio
async def test_post_api_auth_register_missing_credentials_returns_400(quart_app_with_routes: Quart):
    """POST /api/auth/register without username/password returns 400."""
    client = quart_app_with_routes.test_client()
    response = await client.post(
        "/api/auth/register",
        json={},
    )
    assert response.status_code == 400
    data = await response.get_json()
    assert "error" in data


@pytest.mark.asyncio
async def test_post_api_admin_check_with_admin_token_returns_200_and_is_admin(quart_app_with_routes: Quart, db):
    """POST /api/admin/check with valid admin auth returns 200 and is_admin in JSON."""
    client = quart_app_with_routes.test_client()
    # Register a user and get token
    reg = await client.post(
        "/api/auth/register",
        json={"username": "admincheckuser", "password": "pass1234"},
    )
    assert reg.status_code == 200
    reg_data = await reg.get_json()
    token = reg_data.get("token")
    user_id = reg_data.get("user_id")
    assert token and user_id
    # Patch async admin check where used: admin_common and admin_check
    async def mock_admin_async(*args, **kwargs):
        return True
    with patch("bot.web.routes.admin_common.check_admin_access_async", side_effect=mock_admin_async), patch(
        "bot.web.routes.admin_check.check_admin_access_async", side_effect=mock_admin_async
    ):
        response = await client.post(
            "/api/admin/check",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )
    assert response.status_code == 200
    data = await response.get_json()
    assert data.get("success") is True
    assert data.get("is_admin") is True
