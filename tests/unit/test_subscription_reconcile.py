"""Unit tests: panel snapshot helpers, list snapshot shape, reconcile_client fast path."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.services.subscription_manager import (
    clients_by_email_from_xui_list_response,
    panel_entry_from_snapshot,
)
from bot.services.xui_service import (
    _panel_snapshot_matches_desired,
    _flow_matches_desired,
)


def test_clients_by_email_includes_flow_and_protocol():
    ms = 1_700_000_000_000
    payload = {
        "obj": [
            {
                "protocol": "vless",
                "settings": json.dumps(
                    {
                        "clients": [
                            {
                                "email": "u@x",
                                "expiryTime": ms,
                                "limitIp": 3,
                                "flow": "xtls-rprx-vision",
                            }
                        ]
                    }
                ),
            }
        ]
    }
    m = clients_by_email_from_xui_list_response(payload)
    assert "u@x" in m
    assert m["u@x"]["flow"] == "xtls-rprx-vision"
    assert m["u@x"]["protocol"] == "vless"
    assert m["u@x"]["limit_ip"] == 3
    assert m["u@x"]["expiry_sec"] == ms // 1000


def test_panel_entry_from_snapshot_roundtrip():
    email_map = {
        "a@b": {
            "expiry_sec": 100,
            "limit_ip": 2,
            "flow": "x",
            "protocol": "vless",
        }
    }
    pe = panel_entry_from_snapshot(email_map, "a@b")
    assert pe["on_panel"] is True
    assert pe["flow"] == "x"
    assert pe["protocol"] == "vless"
    assert _panel_snapshot_matches_desired(pe, 100, 2, "x") is True
    assert _panel_snapshot_matches_desired(pe, 100, 2, "y") is False


def test_flow_matches_desired_trojan_ignores_flow():
    assert _flow_matches_desired("trojan", "old", "new") is True


def test_panel_snapshot_matches_trojan_ignores_flow_drift():
    snap = {
        "on_panel": True,
        "expiry_sec": 50,
        "limit_ip": 1,
        "flow": "should-ignore",
        "protocol": "trojan",
    }
    assert _panel_snapshot_matches_desired(snap, 50, 1, "xtls") is True


@pytest.mark.asyncio
async def test_reconcile_client_fast_path_skips_get_by_email():
    """При полном совпадении снимка reconcile не вызывает get_by_email."""
    with patch("bot.services.xui_service.PY3XUI_AVAILABLE", True):
        with patch("bot.services.xui_service.AsyncApi"):
            from bot.services.xui_service import X3

            x3 = X3.__new__(X3)
            x3._logged_in = True
            x3._api = MagicMock()
            x3._api.client.get_by_email = AsyncMock()
            x3._api.login = AsyncMock()
            x3._ensure_login = AsyncMock()

            snap = {
                "on_panel": True,
                "expiry_sec": 2000,
                "limit_ip": 1,
                "flow": "a",
                "protocol": "vless",
            }
            ok, did_upd = await x3.reconcile_client(
                "u@test",
                expiry_sec=2000,
                limit_ip=1,
                flow_from_config="a",
                panel_snapshot=snap,
            )
            assert ok is True
            assert did_upd is False
            x3._api.client.get_by_email.assert_not_called()
