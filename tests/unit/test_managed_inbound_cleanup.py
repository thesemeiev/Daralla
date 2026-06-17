"""Orphan cleanup respects managed_inbound_ids scope."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from daralla_backend.services.sync_manager import SyncManager
from daralla_backend.services.subscription_manager import SubscriptionManager
from daralla_backend.services.server_manager import MultiServerManager


@pytest.fixture
def dual_inbound_xui():
    xui = MagicMock()
    xui.list = AsyncMock(
        return_value={
            "obj": [
                {
                    "id": 1,
                    "settings": json.dumps({"clients": [{"email": "orphan-managed@test"}]}),
                },
                {
                    "id": 99,
                    "settings": json.dumps({"clients": [{"email": "orphan-cascade@test"}]}),
                },
            ]
        }
    )
    xui.deleteClient = AsyncMock(return_value=True)
    return xui


@pytest.fixture
def scoped_server_manager(dual_inbound_xui):
    server_info = {
        "name": "scoped-server",
        "x3": dual_inbound_xui,
        "config": {"managed_inbound_ids": "[1]"},
        "group_id": None,
    }
    manager = MultiServerManager(servers_by_group=None)
    manager.servers_by_group = {0: [server_info]}
    manager.servers = [server_info]
    return manager


@pytest.mark.asyncio
async def test_cleanup_orphaned_clients_skips_unmanaged_inbounds(
    scoped_server_manager, dual_inbound_xui
):
    with (
        patch(
            "daralla_backend.services.sync_manager.get_subscriptions_to_sync",
            new_callable=AsyncMock,
        ) as m_sync,
        patch(
            "daralla_backend.services.sync_manager.get_subscription_servers",
            new_callable=AsyncMock,
        ) as m_servers,
    ):
        m_sync.return_value = []
        m_servers.return_value = []

        sync_manager = SyncManager(
            scoped_server_manager, SubscriptionManager(scoped_server_manager)
        )
        stats = await sync_manager.cleanup_orphaned_clients()

    assert stats["servers_checked"] == 1
    assert stats["deleted_count"] >= 1
    dual_inbound_xui.deleteClient.assert_any_call("orphan-managed@test")
    for call in dual_inbound_xui.deleteClient.await_args_list:
        assert call.args[0] != "orphan-cascade@test"
