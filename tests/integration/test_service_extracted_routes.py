"""Integration contracts for routes extracted into service layer."""

import base64
import uuid
from unittest.mock import patch

import pytest
from quart import Quart

from bot.app_context import AppContext, set_ctx
from bot.web.app_quart import create_quart_app


@pytest.fixture
def quart_app_with_routes():
    """Quart app with all blueprints registered."""
    return create_quart_app(bot_app=object())


async def _auth_ok(*args, **kwargs):
    return "1"


async def _admin_ok(*args, **kwargs):
    return True


async def _admin_post(client, path: str, payload: dict):
    with patch("bot.web.routes.admin_common.authenticate_request_async", side_effect=_auth_ok), patch(
        "bot.web.routes.admin_common.check_admin_access_async", side_effect=_admin_ok
    ):
        return await client.post(path, json=payload)


@pytest.mark.asyncio
async def test_subscription_unknown_token_returns_404_when_manager_available(
    quart_app_with_routes: Quart, db
):
    set_ctx(AppContext(subscription_manager=object(), vpn_brand_name="Daralla VPN"))
    client = quart_app_with_routes.test_client()
    response = await client.get("/sub/unknown_token_12345")
    assert response.status_code == 404
    assert (await response.get_data(as_text=True)) == "Subscription not found"


@pytest.mark.asyncio
async def test_subscription_returns_503_without_subscription_manager(
    quart_app_with_routes: Quart, db
):
    set_ctx(AppContext(subscription_manager=None, vpn_brand_name="Daralla VPN"))
    client = quart_app_with_routes.test_client()
    response = await client.get("/sub/unknown_token_12345")
    assert response.status_code == 503
    assert (await response.get_data(as_text=True)) == "Service unavailable"


@pytest.mark.asyncio
async def test_admin_server_groups_list_returns_success(
    quart_app_with_routes: Quart, db
):
    set_ctx(AppContext())
    client = quart_app_with_routes.test_client()
    response = await _admin_post(client, "/api/admin/server-groups", {"action": "list"})
    assert response.status_code == 200
    data = await response.get_json()
    assert data.get("success") is True
    assert "groups" in data
    assert "stats" in data


@pytest.mark.asyncio
async def test_admin_server_groups_add_requires_name(
    quart_app_with_routes: Quart, db
):
    set_ctx(AppContext())
    client = quart_app_with_routes.test_client()
    response = await _admin_post(client, "/api/admin/server-groups", {"action": "add"})
    assert response.status_code == 400
    data = await response.get_json()
    assert data.get("error") == "Name is required"


@pytest.mark.asyncio
async def test_admin_server_config_sync_flow_requires_server_id(
    quart_app_with_routes: Quart, db
):
    set_ctx(AppContext())
    client = quart_app_with_routes.test_client()
    response = await _admin_post(client, "/api/admin/server-config/sync-flow", {})
    assert response.status_code == 400
    data = await response.get_json()
    assert data.get("error") == "server_id is required"


@pytest.mark.asyncio
async def test_admin_servers_add_update_delete_contract(
    quart_app_with_routes: Quart, db
):
    set_ctx(AppContext())
    client = quart_app_with_routes.test_client()
    suffix = uuid.uuid4().hex[:8]

    add_group_resp = await _admin_post(
        client,
        "/api/admin/server-groups",
        {"action": "add", "name": f"group-{suffix}", "description": "test"},
    )
    assert add_group_resp.status_code == 200
    add_group_data = await add_group_resp.get_json()
    group_id = add_group_data.get("group_id")
    assert add_group_data.get("success") is True
    assert isinstance(group_id, int)

    add_server_resp = await _admin_post(
        client,
        "/api/admin/servers-config",
        {
            "action": "add",
            "group_id": group_id,
            "name": f"srv-{suffix}",
            "host": "127.0.0.1",
            "login": "admin",
            "password": "admin",
            "is_active": 0,
        },
    )
    assert add_server_resp.status_code == 200
    add_server_data = await add_server_resp.get_json()
    server_id = add_server_data.get("server_id")
    assert add_server_data.get("success") is True
    assert isinstance(server_id, int)

    update_resp = await _admin_post(
        client,
        "/api/admin/server-config/update",
        {"id": server_id, "display_name": "Updated Name"},
    )
    assert update_resp.status_code == 200
    update_data = await update_resp.get_json()
    assert update_data.get("success") is True
    assert update_data.get("server_id") == server_id
    assert update_data.get("client_flow_changed") is False

    delete_resp = await _admin_post(
        client,
        "/api/admin/server-config/delete",
        {"id": server_id},
    )
    assert delete_resp.status_code == 200
    delete_data = await delete_resp.get_json()
    assert delete_data.get("success") is True
    assert isinstance(delete_data.get("sync_error"), str)


@pytest.mark.asyncio
async def test_admin_servers_reorder_contract(
    quart_app_with_routes: Quart, db
):
    set_ctx(AppContext())
    client = quart_app_with_routes.test_client()
    suffix = uuid.uuid4().hex[:8]

    add_group_resp = await _admin_post(
        client,
        "/api/admin/server-groups",
        {"action": "add", "name": f"reorder-group-{suffix}", "description": "test"},
    )
    group_id = (await add_group_resp.get_json()).get("group_id")

    add_first_resp = await _admin_post(
        client,
        "/api/admin/servers-config",
        {
            "action": "add",
            "group_id": group_id,
            "name": f"reorder-srv-a-{suffix}",
            "host": "127.0.0.1",
            "login": "admin",
            "password": "admin",
            "is_active": 0,
        },
    )
    first_id = (await add_first_resp.get_json()).get("server_id")

    add_second_resp = await _admin_post(
        client,
        "/api/admin/servers-config",
        {
            "action": "add",
            "group_id": group_id,
            "name": f"reorder-srv-b-{suffix}",
            "host": "127.0.0.1",
            "login": "admin",
            "password": "admin",
            "is_active": 0,
        },
    )
    second_id = (await add_second_resp.get_json()).get("server_id")

    reorder_resp = await _admin_post(
        client,
        "/api/admin/servers-config",
        {"action": "reorder", "group_id": group_id, "server_ids": [second_id, first_id]},
    )
    assert reorder_resp.status_code == 200
    reorder_data = await reorder_resp.get_json()
    assert reorder_data.get("success") is True

    list_resp = await _admin_post(
        client,
        "/api/admin/servers-config",
        {"action": "list", "group_id": group_id},
    )
    assert list_resp.status_code == 200
    list_data = await list_resp.get_json()
    assert list_data.get("success") is True
    ids = [item["id"] for item in list_data.get("servers", [])]
    assert ids[:2] == [second_id, first_id]


@pytest.mark.asyncio
async def test_admin_commerce_get_contract(quart_app_with_routes: Quart, db):
    set_ctx(AppContext())
    client = quart_app_with_routes.test_client()
    response = await _admin_post(client, "/api/admin/commerce", {})
    assert response.status_code == 200
    data = await response.get_json()
    assert data.get("success") is True
    assert isinstance(data.get("price_month"), int)
    assert isinstance(data.get("price_3month"), int)
    assert isinstance(data.get("default_device_limit"), int)


@pytest.mark.asyncio
async def test_admin_commerce_update_validation_contract(quart_app_with_routes: Quart, db):
    set_ctx(AppContext())
    client = quart_app_with_routes.test_client()
    response = await _admin_post(
        client,
        "/api/admin/commerce",
        {"price_month": -1, "price_3month": 350, "default_device_limit": 1},
    )
    assert response.status_code == 400
    data = await response.get_json()
    assert data.get("success") is False
    assert "error" in data


@pytest.mark.asyncio
async def test_admin_commerce_update_success_contract(quart_app_with_routes: Quart, db):
    set_ctx(AppContext())
    client = quart_app_with_routes.test_client()
    response = await _admin_post(
        client,
        "/api/admin/commerce",
        {"price_month": 222, "price_3month": 555, "default_device_limit": 3},
    )
    assert response.status_code == 200
    data = await response.get_json()
    assert data.get("success") is True
    assert data.get("price_month") == 222
    assert data.get("price_3month") == 555
    assert data.get("default_device_limit") == 3


class _FakeSubscriptionManager:
    async def build_vless_links_for_subscription(self, sub_id):
        assert sub_id == 101
        return ["vless://uuid@example.com:443?encryption=none#Daralla-Test"]


@pytest.mark.asyncio
async def test_subscription_positive_contract_with_mocked_dependencies(
    quart_app_with_routes: Quart, db
):
    set_ctx(
        AppContext(
            subscription_manager=_FakeSubscriptionManager(),
            server_manager=None,
            vpn_brand_name="Daralla VPN",
        )
    )
    client = quart_app_with_routes.test_client()
    with patch(
        "bot.services.subscription_route_service.get_subscription_by_token",
        return_value={"id": 101, "status": "active", "expires_at": 1893456000},
    ), patch(
        "bot.services.subscription_route_service.get_subscription_servers",
        return_value=[{"server_name": "srv-1", "client_email": "u1@example.com"}],
    ), patch(
        "bot.services.subscription_route_service.is_subscription_active",
        return_value=True,
    ):
        response = await client.get("/sub/token-101")
    assert response.status_code == 200
    body = await response.get_data(as_text=True)
    decoded = base64.b64decode(body).decode("utf-8")
    assert "vless://uuid@example.com:443?encryption=none#Daralla-Test" in decoded
    assert response.headers.get("subscription-userinfo")
    assert response.headers.get("profile-title")
