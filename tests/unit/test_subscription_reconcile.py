"""Unit tests: panel snapshot helpers, list snapshot shape, reconcile_client."""
import json
from unittest.mock import AsyncMock, MagicMock

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


def _inbound_dict(inv_id: int, protocol: str, clients: list) -> dict:
    """Build a panel-shaped inbound dict for mocking _panel.list_inbounds."""
    return {
        "id": inv_id,
        "protocol": protocol,
        "settings": json.dumps({"clients": clients}),
    }


def _make_x3():
    """Create a bare X3 with a mocked panel client."""
    from daralla_backend.services.xui_service import X3
    x3 = X3.__new__(X3)
    x3._panel = MagicMock()
    x3._ensure_login = AsyncMock()
    x3._post_inbound_update_client = AsyncMock()
    return x3


@pytest.mark.asyncio
async def test_reconcile_client_applies_flow_from_config_when_mismatch():
    """Reconcile проходит через snapshot list_inbounds: один inbound, update с inbound_id_override."""
    x3 = _make_x3()
    inv = _inbound_dict(
        7, "vless",
        [{"email": "u@test", "id": "uuid", "expiryTime": 2000 * 1000, "limitIp": 1, "flow": ""}],
    )
    x3._panel.list_inbounds = AsyncMock(return_value=[inv])

    ok, did_upd = await x3.reconcile_client(
        "u@test",
        expiry_sec=2000,
        limit_ip=1,
        flow_from_config="xtls-rprx-vision",
    )
    assert ok is True
    assert did_upd is True
    x3._post_inbound_update_client.assert_called_once()
    ca = x3._post_inbound_update_client.call_args
    assert ca.kwargs.get("inbound_id_override") == 7
    assert ca.kwargs.get("flow_override") == "xtls-rprx-vision"


@pytest.mark.asyncio
async def test_reconcile_client_always_posts_even_when_api_looks_in_sync():
    """Каждый reconcile по списку inbound шлёт update + flow_override."""
    x3 = _make_x3()
    inv = _inbound_dict(
        1, "vless",
        [{"email": "u@test", "id": "uuid", "expiryTime": 2000 * 1000, "limitIp": 1, "flow": "a"}],
    )
    x3._panel.list_inbounds = AsyncMock(return_value=[inv])

    ok, did_upd = await x3.reconcile_client(
        "u@test",
        expiry_sec=2000,
        limit_ip=1,
        flow_from_config="a",
    )
    assert ok is True
    assert did_upd is True
    x3._post_inbound_update_client.assert_called_once()
    assert x3._post_inbound_update_client.call_args.kwargs.get("flow_override") == "a"


@pytest.mark.asyncio
async def test_reconcile_client_updates_same_email_in_every_inbound():
    """Один email в двух inbound — два updateClient с разным inbound_id_override."""
    x3 = _make_x3()
    inv_a = _inbound_dict(
        10, "vless",
        [{"email": "x@y", "id": "u1", "expiryTime": 0, "limitIp": 1, "flow": ""}],
    )
    inv_b = _inbound_dict(
        20, "vless",
        [{"email": "x@y", "id": "u2", "expiryTime": 0, "limitIp": 1, "flow": ""}],
    )
    x3._panel.list_inbounds = AsyncMock(return_value=[inv_a, inv_b])

    ok, did_upd = await x3.reconcile_client(
        "x@y",
        expiry_sec=100,
        limit_ip=2,
        flow_from_config="xtls-rprx-vision",
    )
    assert ok is True
    assert did_upd is True
    assert x3._post_inbound_update_client.await_count == 2
    calls = x3._post_inbound_update_client.await_args_list
    ids = sorted(c.kwargs.get("inbound_id_override") for c in calls)
    assert ids == [10, 20]


@pytest.mark.asyncio
async def test_reconcile_client_returns_false_when_email_not_found():
    """Пустой список inbound / нет email в clients — reconcile сообщает False."""
    x3 = _make_x3()
    x3._panel.list_inbounds = AsyncMock(return_value=[])

    ok, did_upd = await x3.reconcile_client(
        "orphan@test",
        expiry_sec=100,
        limit_ip=2,
        flow_from_config="",
    )
    assert ok is False
    assert did_upd is False
    x3._post_inbound_update_client.assert_not_called()
