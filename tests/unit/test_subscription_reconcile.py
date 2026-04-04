"""Unit tests: panel snapshot helpers, list snapshot shape, reconcile_client."""
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


def test_flow_matches_desired_compares_panel_to_config():
    assert _flow_matches_desired("old", "new") is False
    assert _flow_matches_desired("x", "x") is True
    assert _flow_matches_desired("", None) is True


def test_panel_snapshot_matches_requires_flow_for_trojan():
    snap = {
        "on_panel": True,
        "expiry_sec": 50,
        "limit_ip": 1,
        "flow": "should-ignore",
        "protocol": "trojan",
    }
    assert _panel_snapshot_matches_desired(snap, 50, 1, "xtls") is False
    assert _panel_snapshot_matches_desired(snap, 50, 1, "should-ignore") is True


@pytest.mark.asyncio
async def test_reconcile_client_applies_flow_from_config_when_mismatch():
    """При расхождении flow с конфигом сервера — update; без fast path по протоколу."""
    with patch("bot.services.xui_service.PY3XUI_AVAILABLE", True):
        with patch("bot.services.xui_service.AsyncApi"):
            from bot.services.xui_service import X3

            x3 = X3.__new__(X3)
            x3._logged_in = True
            x3._api = MagicMock()
            mock_c = MagicMock()
            mock_c.expiry_time = 2000 * 1000
            mock_c.limit_ip = 1
            mock_c.flow = ""
            mock_c.id = "uuid"
            x3._api.client.get_by_email = AsyncMock(return_value=mock_c)
            x3._api.login = AsyncMock()
            x3._ensure_login = AsyncMock()
            x3._ensure_client_id_for_update = MagicMock(side_effect=lambda c: c)
            x3._post_inbound_update_client = AsyncMock()

            ok, did_upd = await x3.reconcile_client(
                "u@test",
                expiry_sec=2000,
                limit_ip=1,
                flow_from_config="xtls-rprx-vision",
            )
            assert ok is True
            assert did_upd is True
            x3._api.client.get_by_email.assert_called_once()
            assert mock_c.flow == "xtls-rprx-vision"
            x3._post_inbound_update_client.assert_called_once()
            call_kw = x3._post_inbound_update_client.call_args
            assert call_kw.kwargs.get("flow_override") == "xtls-rprx-vision"


@pytest.mark.asyncio
async def test_reconcile_client_always_posts_even_when_api_looks_in_sync():
    """Даже если get_by_email совпадает с целью — всё равно update + flow_override (API про flow врёт)."""
    with patch("bot.services.xui_service.PY3XUI_AVAILABLE", True):
        with patch("bot.services.xui_service.AsyncApi"):
            from bot.services.xui_service import X3

            x3 = X3.__new__(X3)
            x3._logged_in = True
            x3._api = MagicMock()
            mock_c = MagicMock()
            mock_c.expiry_time = 2000 * 1000
            mock_c.limit_ip = 1
            mock_c.flow = "a"
            mock_c.id = "uuid"
            x3._api.client.get_by_email = AsyncMock(return_value=mock_c)
            x3._api.login = AsyncMock()
            x3._ensure_login = AsyncMock()
            x3._ensure_client_id_for_update = MagicMock(side_effect=lambda c: c)
            x3._post_inbound_update_client = AsyncMock()

            ok, did_upd = await x3.reconcile_client(
                "u@test",
                expiry_sec=2000,
                limit_ip=1,
                flow_from_config="a",
            )
            assert ok is True
            assert did_upd is True
            x3._api.client.get_by_email.assert_called_once()
            x3._post_inbound_update_client.assert_called_once()
            assert x3._post_inbound_update_client.call_args.kwargs.get("flow_override") == "a"
