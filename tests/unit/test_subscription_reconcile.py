"""Unit tests: panel snapshot helpers, list snapshot shape, reconcile_client."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from daralla_backend.services.subscription_manager import (
    clients_by_email_from_xui_list_response,
    panel_entry_from_snapshot,
)
from daralla_backend.services.xui_service import (
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
    """Reconcile обходит get_list: один inbound, update с inbound_id_override."""
    with patch("daralla_backend.services.xui_service.PY3XUI_AVAILABLE", True):
        with patch("daralla_backend.services.xui_service.AsyncApi"):
            from daralla_backend.services.xui_service import X3

            x3 = X3.__new__(X3)
            x3._logged_in = True
            x3._api = MagicMock()
            mock_c = MagicMock()
            mock_c.email = "u@test"
            mock_c.expiry_time = 2000 * 1000
            mock_c.limit_ip = 1
            mock_c.flow = ""
            mock_c.id = "uuid"
            inv = MagicMock()
            inv.id = 7
            inv.settings = MagicMock(clients=[mock_c])
            x3._api.inbound.get_list = AsyncMock(return_value=[inv])
            x3._api.client.get_by_email = AsyncMock()
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
            x3._api.client.get_by_email.assert_not_called()
            assert mock_c.flow == "xtls-rprx-vision"
            x3._post_inbound_update_client.assert_called_once()
            ca = x3._post_inbound_update_client.call_args
            assert ca.kwargs.get("inbound_id_override") == 7
            assert ca.kwargs.get("flow_override") == "xtls-rprx-vision"


@pytest.mark.asyncio
async def test_reconcile_client_always_posts_even_when_api_looks_in_sync():
    """Каждый reconcile по списку inbound шлёт update + flow_override."""
    with patch("daralla_backend.services.xui_service.PY3XUI_AVAILABLE", True):
        with patch("daralla_backend.services.xui_service.AsyncApi"):
            from daralla_backend.services.xui_service import X3

            x3 = X3.__new__(X3)
            x3._logged_in = True
            x3._api = MagicMock()
            mock_c = MagicMock()
            mock_c.email = "u@test"
            mock_c.expiry_time = 2000 * 1000
            mock_c.limit_ip = 1
            mock_c.flow = "a"
            mock_c.id = "uuid"
            inv = MagicMock()
            inv.id = 1
            inv.settings = MagicMock(clients=[mock_c])
            x3._api.inbound.get_list = AsyncMock(return_value=[inv])
            x3._api.client.get_by_email = AsyncMock()
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
            x3._api.client.get_by_email.assert_not_called()
            x3._post_inbound_update_client.assert_called_once()
            assert x3._post_inbound_update_client.call_args.kwargs.get("flow_override") == "a"


@pytest.mark.asyncio
async def test_reconcile_client_updates_same_email_in_every_inbound():
    """Один email в двух inbound — два updateClient с разным inbound_id_override."""
    with patch("daralla_backend.services.xui_service.PY3XUI_AVAILABLE", True):
        with patch("daralla_backend.services.xui_service.AsyncApi"):
            from daralla_backend.services.xui_service import X3

            x3 = X3.__new__(X3)
            x3._logged_in = True
            x3._api = MagicMock()
            c1 = MagicMock(email="x@y", id="u1", expiry_time=0, limit_ip=1, flow="")
            c2 = MagicMock(email="x@y", id="u2", expiry_time=0, limit_ip=1, flow="")
            inv_a = MagicMock(id=10, settings=MagicMock(clients=[c1]))
            inv_b = MagicMock(id=20, settings=MagicMock(clients=[c2]))
            x3._api.inbound.get_list = AsyncMock(return_value=[inv_a, inv_b])
            x3._api.client.get_by_email = AsyncMock()
            x3._api.login = AsyncMock()
            x3._ensure_login = AsyncMock()
            x3._ensure_client_id_for_update = MagicMock(side_effect=lambda c: c)
            x3._post_inbound_update_client = AsyncMock()

            ok, did_upd = await x3.reconcile_client(
                "x@y",
                expiry_sec=100,
                limit_ip=2,
                flow_from_config="xtls-rprx-vision",
            )
            assert ok is True
            assert did_upd is True
            x3._api.client.get_by_email.assert_not_called()
            assert x3._post_inbound_update_client.await_count == 2
            calls = x3._post_inbound_update_client.await_args_list
            ids = sorted(c.kwargs.get("inbound_id_override") for c in calls)
            assert ids == [10, 20]


@pytest.mark.asyncio
async def test_reconcile_client_fallback_get_by_email_when_not_in_list():
    """Пустой список inbound / нет email в clients — fallback на get_by_email."""
    with patch("daralla_backend.services.xui_service.PY3XUI_AVAILABLE", True):
        with patch("daralla_backend.services.xui_service.AsyncApi"):
            from daralla_backend.services.xui_service import X3

            x3 = X3.__new__(X3)
            x3._logged_in = True
            x3._api = MagicMock()
            mock_c = MagicMock()
            mock_c.expiry_time = 0
            mock_c.limit_ip = 1
            mock_c.flow = ""
            mock_c.id = "uuid"
            mock_c.inbound_id = 5
            x3._api.inbound.get_list = AsyncMock(return_value=[])
            x3._api.client.get_by_email = AsyncMock(return_value=mock_c)
            x3._api.login = AsyncMock()
            x3._ensure_login = AsyncMock()
            x3._ensure_client_id_for_update = MagicMock(side_effect=lambda c: c)
            x3._post_inbound_update_client = AsyncMock()

            ok, did_upd = await x3.reconcile_client(
                "orphan@test",
                expiry_sec=100,
                limit_ip=2,
                flow_from_config="",
            )
            assert ok is True
            assert did_upd is True
            x3._api.client.get_by_email.assert_called_once_with("orphan@test")
            x3._post_inbound_update_client.assert_called_once()
