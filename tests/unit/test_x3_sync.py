"""
Unit tests for X3/sync: deleteClient return value and ensure_client_on_server with mocks.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.services.sync_manager import SyncManager
from bot.services.subscription_manager import SubscriptionManager
from bot.services.server_manager import MultiServerManager


@pytest.fixture
def mock_xui():
    """X3-like mock: list(), deleteClient(email) with configurable return values."""
    xui = MagicMock()
    xui.list = AsyncMock(return_value={
        "obj": [
            {"settings": json.dumps({"clients": [{"email": "orphan@test"}]})}
        ]
    })
    # deleteClient: first call True (one client deleted), second call False (no more clients)
    xui.deleteClient = AsyncMock(side_effect=[True, False])
    return xui


@pytest.fixture
def server_manager_with_mock_xui(mock_xui):
    """MultiServerManager with one server that has mock_xui (no real X3)."""
    server_info = {
        "name": "test-server",
        "x3": mock_xui,
        "config": {},
        "group_id": None,
    }
    manager = MultiServerManager(servers_by_group=None)
    manager.servers_by_group = {0: [server_info]}
    manager.servers = [server_info]
    return manager


@pytest.mark.asyncio
async def test_cleanup_orphaned_clients_deleteClient_true_then_false(
    server_manager_with_mock_xui, mock_xui
):
    """
    cleanup_orphaned_clients: when deleteClient returns True then False,
    deleted_count is 1 and loop stops (no infinite loop).
    """
    with (
        patch("bot.services.sync_manager.get_subscriptions_to_sync", new_callable=AsyncMock) as m_sync,
        patch("bot.services.sync_manager.get_subscription_servers", new_callable=AsyncMock) as m_servers,
    ):
        m_sync.return_value = []  # no subscriptions in DB -> all clients are orphans
        m_servers.return_value = []

        subscription_manager = SubscriptionManager(server_manager_with_mock_xui)
        sync_manager = SyncManager(server_manager_with_mock_xui, subscription_manager)

        stats = await sync_manager.cleanup_orphaned_clients()

    assert stats["servers_checked"] == 1
    assert stats["deleted_count"] == 1
    assert stats["errors"] == []
    # deleteClient called for orphan@test: first True (counted), second False (break)
    assert mock_xui.deleteClient.await_count == 2
    mock_xui.deleteClient.assert_any_call("orphan@test")


@pytest.fixture
def mock_xui_for_ensure():
    """X3 mock for ensure_client_on_server: client does not exist, addClient succeeds."""
    xui = MagicMock()
    xui.client_exists = AsyncMock(return_value=False)
    xui.addClient = AsyncMock(return_value=True)
    # ensure_client_on_server после addClient теперь делает reconcile_client (может ретраить до 3 раз)
    xui.reconcile_client = AsyncMock(return_value=(True, True))
    return xui


@pytest.fixture
def server_manager_for_ensure(mock_xui_for_ensure):
    """MultiServerManager that returns mock_xui for get_server_by_name('srv1')."""
    manager = MultiServerManager(servers_by_group=None)
    server_info = {
        "name": "srv1",
        "x3": mock_xui_for_ensure,
        "config": {},
        "group_id": None,
    }
    manager.servers_by_group = {0: [server_info]}
    manager.servers = [server_info]
    return manager


@pytest.mark.asyncio
async def test_ensure_client_on_server_creates_client_when_addClient_succeeds(
    server_manager_for_ensure, mock_xui_for_ensure
):
    """
    ensure_client_on_server: when client does not exist and addClient returns True,
    result is (True, True) — client exists/created and was created in this call.
    """
    subscription_manager = SubscriptionManager(server_manager_for_ensure)

    result = await subscription_manager.ensure_client_on_server(
        subscription_id=1,
        server_name="srv1",
        client_email="user@test",
        user_id="123",
        expires_at=2000000000,
        token="sub_token",
        device_limit=1,
    )

    assert result == (True, True)
    mock_xui_for_ensure.client_exists.assert_awaited_once_with("user@test")
    mock_xui_for_ensure.addClient.assert_awaited_once()
    assert mock_xui_for_ensure.reconcile_client.await_count >= 1
