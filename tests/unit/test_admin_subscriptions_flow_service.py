"""Unit tests for admin subscription sync flow behavior."""

import logging
from unittest.mock import AsyncMock, Mock

import pytest

from daralla_backend.services import admin_subscriptions_flow_service as flow


@pytest.mark.asyncio
async def test_sync_after_update_keeps_server_links_on_expired(monkeypatch):
    """Expired should delete panel clients but keep subscription_servers links."""
    xui = AsyncMock()
    xui.deleteClient = AsyncMock(return_value=True)
    server_manager = Mock()
    server_manager.get_server_by_name.return_value = (xui, "srv-1")

    sub_mgr = AsyncMock()
    sub_mgr.ensure_client_on_server = AsyncMock(return_value=(True, True))
    managers = {"server_manager": server_manager, "subscription_manager": sub_mgr}

    monkeypatch.setattr(flow, "get_globals", lambda: managers)
    monkeypatch.setattr(
        flow,
        "get_subscription_servers",
        AsyncMock(return_value=[{"server_name": "srv-1", "client_email": "u1_1"}]),
    )
    monkeypatch.setattr(flow, "get_user_id_from_subscriber_id", AsyncMock(return_value="u1"))
    remove_mock = AsyncMock()
    monkeypatch.setattr(flow, "remove_subscription_server", remove_mock)

    await flow._sync_after_update(
        sub_id=1,
        updated_sub={
            "subscriber_id": 10,
            "status": "expired",
            "expires_at": 100,
            "device_limit": 1,
            "subscription_token": "tok",
        },
        old_status="active",
        old_expires_at=200,
        old_device_limit=1,
        updates={"expires_at": 100},
        logger=logging.getLogger("test"),
    )

    remove_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_after_update_removes_server_links_on_deleted(monkeypatch):
    """Deleted should remove subscription_servers links."""
    xui = AsyncMock()
    xui.deleteClient = AsyncMock(return_value=True)
    server_manager = Mock()
    server_manager.get_server_by_name.return_value = (xui, "srv-1")

    sub_mgr = AsyncMock()
    sub_mgr.ensure_client_on_server = AsyncMock(return_value=(True, True))
    managers = {"server_manager": server_manager, "subscription_manager": sub_mgr}

    monkeypatch.setattr(flow, "get_globals", lambda: managers)
    monkeypatch.setattr(
        flow,
        "get_subscription_servers",
        AsyncMock(return_value=[{"server_name": "srv-1", "client_email": "u1_1"}]),
    )
    monkeypatch.setattr(flow, "get_user_id_from_subscriber_id", AsyncMock(return_value="u1"))
    remove_mock = AsyncMock()
    monkeypatch.setattr(flow, "remove_subscription_server", remove_mock)

    await flow._sync_after_update(
        sub_id=1,
        updated_sub={
            "subscriber_id": 10,
            "status": "deleted",
            "expires_at": 100,
            "device_limit": 1,
            "subscription_token": "tok",
        },
        old_status="active",
        old_expires_at=200,
        old_device_limit=1,
        updates={"status": "deleted"},
        logger=logging.getLogger("test"),
    )

    assert remove_mock.await_count == 1
