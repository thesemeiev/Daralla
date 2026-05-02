from unittest.mock import AsyncMock

import pytest

from daralla_backend.services.xui_service import X3


class _Inbound:
    def __init__(self, inbound_id: int, protocol: str, version: int | None = None):
        self.id = inbound_id
        self.protocol = protocol
        self.settings = type("Settings", (), {"version": version})() if version is not None else None


@pytest.mark.asyncio
async def test_resolve_target_inbound_prefers_requested_protocol():
    x3 = X3.__new__(X3)
    inbounds = [_Inbound(1, "vless"), _Inbound(2, "hysteria2")]
    inbound_id, protocol, error = await x3._resolve_target_inbound(
        inbounds=inbounds,
        target_protocol="hysteria2",
        inbound_id=None,
    )
    assert error is None
    assert inbound_id == 2
    assert protocol == "hysteria2"


@pytest.mark.asyncio
async def test_resolve_target_inbound_maps_hysteria_v2_to_hysteria2():
    x3 = X3.__new__(X3)
    inbounds = [_Inbound(1, "hysteria", version=2)]
    inbound_id, protocol, error = await x3._resolve_target_inbound(
        inbounds=inbounds,
        target_protocol="hysteria2",
        inbound_id=None,
    )
    assert error is None
    assert inbound_id == 1
    assert protocol == "hysteria2"


def _panel_inbound_dict(inv_id: int, protocol: str) -> dict:
    """Panel-shaped inbound dict: id + protocol; settings/version optional."""
    return {"id": inv_id, "protocol": protocol, "settings": "{}"}


@pytest.mark.asyncio
async def test_add_client_returns_typed_error_for_unsupported_target():
    x3 = X3.__new__(X3)
    x3._panel = type("Panel", (), {})()
    x3._panel.list_inbounds = AsyncMock(
        return_value=[_panel_inbound_dict(10, "vless")]
    )
    x3._post_inbound_add_clients = AsyncMock()

    result = await x3.addClient(
        day=1,
        tg_id="1",
        user_email="u@example.com",
        target_protocol="hysteria2",
    )

    assert result["ok"] is False
    assert result["reason"] == "unsupported_protocol"
    x3._post_inbound_add_clients.assert_not_called()


@pytest.mark.asyncio
async def test_add_client_hysteria2_uses_auth_payload_without_flow():
    x3 = X3.__new__(X3)
    x3._panel = type("Panel", (), {})()
    x3._panel.list_inbounds = AsyncMock(
        return_value=[_panel_inbound_dict(7, "hysteria2")]
    )
    x3._post_inbound_add_clients = AsyncMock()

    result = await x3.addClient(
        day=1,
        tg_id="1",
        user_email="u@example.com",
        target_protocol="hysteria2",
        flow="xtls-rprx-vision",
    )

    assert result["ok"] is True
    assert result["protocol"] == "hysteria2"
    payload = x3._post_inbound_add_clients.await_args.args[1][0]
    assert payload["protocol"] == "hysteria2"
    assert "auth" in payload
    assert "flow" not in payload
