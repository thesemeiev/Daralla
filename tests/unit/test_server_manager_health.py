"""MultiServerManager.check_server_health: восстановление после x3=None."""
import datetime
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from daralla_backend.services.server_manager import MultiServerManager


@pytest.mark.asyncio
async def test_check_server_health_recreates_x3_after_long_outage():
    """
    После >3 неудач x3 обнуляется. Раньше при consecutive_failures>=3 и force_check=False
    пересоздание X3 не выполнялось — нода не оживала без рестарта. После фикса при
    прохождении circuit breaker cooldown должен создаваться новый клиент и вызываться list_quick.
    """
    config = {
        "name": "node-a",
        "login": "u",
        "password": "p",
        "host": "https://example.com:2053/path",
        "group_id": 1,
    }
    manager = MultiServerManager({1: [config]})
    server_info = manager.servers[0]
    server_info["x3"] = None
    manager.server_health["node-a"] = {
        "status": "offline",
        "last_check": datetime.datetime.now() - datetime.timedelta(seconds=400),
        "last_error": "timeout",
        "consecutive_failures": 5,
        "uptime_percentage": 0.0,
    }
    manager._health_check_cache["node-a"] = {
        "result": False,
        "timestamp": time.time() - 60,
        "cached": True,
    }

    new_x3 = MagicMock()
    new_x3.list_quick = AsyncMock(return_value={"obj": []})

    with patch("daralla_backend.services.server_manager.X3", return_value=new_x3) as x3_cls:
        ok = await manager.check_server_health("node-a", force_check=False)

    assert ok is True
    x3_cls.assert_called_once()
    new_x3.list_quick.assert_awaited_once()
    assert server_info["x3"] is new_x3
    assert manager.server_health["node-a"]["consecutive_failures"] == 0
    assert manager.server_health["node-a"]["status"] == "online"
