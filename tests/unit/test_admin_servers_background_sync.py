"""Admin server save should not block HTTP on full panel sync."""
from unittest.mock import AsyncMock, patch

import pytest

from daralla_backend.services import admin_servers_service as svc


@pytest.mark.asyncio
async def test_reload_and_sync_serialized_starts_background_sync(monkeypatch):
    schedule_mock = patch.object(svc, "_schedule_background_server_sync")
    monkeypatch.setattr(svc, "_reload_server_manager", AsyncMock())

    with schedule_mock as sched:
        extra = await svc._reload_and_sync_serialized(True, sync_reason="test")

    assert extra == {"sync_started": True}
    sched.assert_called_once_with("test")


@pytest.mark.asyncio
async def test_reload_and_sync_serialized_skips_sync_when_not_needed(monkeypatch):
    schedule_mock = patch.object(svc, "_schedule_background_server_sync")
    monkeypatch.setattr(svc, "_reload_server_manager", AsyncMock())

    with schedule_mock as sched:
        extra = await svc._reload_and_sync_serialized(False)

    assert extra == {}
    sched.assert_not_called()
