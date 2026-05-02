"""Unit tests for the standalone XUiPanelClient (no py3xui)."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx
import pytest

from daralla_backend.services.xui_panel_client import XUiPanelClient, XUiPanelError


class _Recorder:
    """Captures the HTTP requests sent through MockTransport."""

    def __init__(self) -> None:
        self.requests: List[httpx.Request] = []
        self.bodies: List[Optional[Dict[str, Any]]] = []


def _make_client(
    handler,
    host: str = "https://panel.example.com:2053/secret",
    *,
    login: str = "admin",
    password: str = "pw",
    max_retries: int = 1,
) -> XUiPanelClient:
    """Builds a client whose internal httpx.AsyncClient uses the given handler."""
    client = XUiPanelClient(
        host=host,
        login=login,
        password=password,
        verify_tls=False,
        max_retries=max_retries,
        session_ttl_sec=3600.0,
    )
    transport = httpx.MockTransport(handler)
    # Replace the underlying client with one wired to MockTransport.
    new_async = httpx.AsyncClient(transport=transport, timeout=client._timeout)
    client._client = new_async
    return client


def _ok(payload: Any = None) -> httpx.Response:
    body: Dict[str, Any] = {"success": True}
    if payload is not None:
        body["obj"] = payload
    return httpx.Response(200, json=body)


def _fail(msg: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json={"success": False, "msg": msg})


@pytest.mark.asyncio
async def test_login_then_list_inbounds_calls_correct_paths():
    rec = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        rec.requests.append(request)
        if request.url.path.endswith("/login"):
            return httpx.Response(200, json={"success": True})
        if request.url.path.endswith("/panel/api/inbounds/list"):
            return _ok([{"id": 1, "protocol": "vless"}])
        return httpx.Response(404, json={"success": False, "msg": "nope"})

    client = _make_client(handler)
    try:
        inbounds = await client.list_inbounds()
    finally:
        await client.aclose()

    assert inbounds == [{"id": 1, "protocol": "vless"}]
    paths = [r.url.path for r in rec.requests]
    assert paths[0].endswith("/login")
    assert paths[1].endswith("/panel/api/inbounds/list")


@pytest.mark.asyncio
async def test_get_inbound_returns_dict_obj():
    inv_obj = {
        "id": 10,
        "protocol": "hysteria2",
        "settings": json.dumps({"clients": [{"email": "u1", "auth": "secret"}]}),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/login"):
            return httpx.Response(200, json={"success": True})
        if request.url.path.endswith("/panel/api/inbounds/get/10"):
            return _ok(inv_obj)
        return _fail("unexpected", status=404)

    client = _make_client(handler)
    try:
        inv = await client.get_inbound(10)
    finally:
        await client.aclose()

    assert inv == inv_obj


@pytest.mark.asyncio
async def test_add_client_sends_settings_with_one_client():
    sent: Dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/login"):
            return httpx.Response(200, json={"success": True})
        if request.url.path.endswith("/panel/api/inbounds/addClient"):
            sent["form"] = dict(httpx.QueryParams(request.read().decode()))
            return _ok()
        return _fail("unexpected", status=404)

    payload = {"email": "u1", "auth": "secret-auth", "enable": True}
    client = _make_client(handler)
    try:
        await client.add_client(7, payload)
    finally:
        await client.aclose()

    assert sent["form"]["id"] == "7"
    settings = json.loads(sent["form"]["settings"])
    assert settings == {"clients": [payload]}


@pytest.mark.asyncio
async def test_update_client_uses_url_id_and_inbound_id_in_body():
    captured: Dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/login"):
            return httpx.Response(200, json={"success": True})
        if "/panel/api/inbounds/updateClient/" in path:
            captured["path"] = path
            captured["form"] = dict(httpx.QueryParams(request.read().decode()))
            return _ok()
        return _fail("unexpected", status=404)

    client = _make_client(handler)
    try:
        await client.update_client(
            client_url_id="hy2-auth-token",
            inbound_id=11,
            client_payload={"email": "u1", "auth": "hy2-auth-token", "enable": True},
        )
    finally:
        await client.aclose()

    assert captured["path"].endswith("/panel/api/inbounds/updateClient/hy2-auth-token")
    assert captured["form"]["id"] == "11"


@pytest.mark.asyncio
async def test_delete_client_and_delete_client_by_email_paths():
    seen_paths: List[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/login"):
            return httpx.Response(200, json={"success": True})
        seen_paths.append(request.url.path)
        return _ok()

    client = _make_client(handler)
    try:
        await client.delete_client(5, "uuid-1234")
        await client.delete_client_by_email(5, "user@example.com")
    finally:
        await client.aclose()

    assert any(p.endswith("/panel/api/inbounds/5/delClient/uuid-1234") for p in seen_paths)
    assert any(
        p.endswith("/panel/api/inbounds/5/delClientByEmail/user@example.com")
        for p in seen_paths
    )


@pytest.mark.asyncio
async def test_relogin_on_401_then_succeeds():
    state = {"calls": 0, "logins": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/login"):
            state["logins"] += 1
            return httpx.Response(200, json={"success": True})
        state["calls"] += 1
        if state["calls"] == 1:
            return httpx.Response(401, json={"success": False, "msg": "session expired"})
        return _ok([])

    client = _make_client(handler, max_retries=3)
    try:
        result = await client.list_inbounds()
    finally:
        await client.aclose()

    assert result == []
    assert state["logins"] == 2
    assert state["calls"] == 2


@pytest.mark.asyncio
async def test_panel_success_false_raises_xui_panel_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/login"):
            return httpx.Response(200, json={"success": True})
        return _fail("Inbound Not Found For Email")

    client = _make_client(handler)
    try:
        with pytest.raises(XUiPanelError) as ei:
            await client.delete_client_by_email(1, "absent@example.com")
    finally:
        await client.aclose()

    assert "not found" in str(ei.value).lower()


@pytest.mark.asyncio
async def test_login_failure_raises_panel_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/login"):
            return httpx.Response(200, json={"success": False, "msg": "bad credentials"})
        return _fail("should-not-reach")

    client = _make_client(handler)
    try:
        with pytest.raises(XUiPanelError) as ei:
            await client.list_inbounds()
    finally:
        await client.aclose()

    assert "bad credentials" in str(ei.value)


@pytest.mark.asyncio
async def test_online_emails_returns_list():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/login"):
            return httpx.Response(200, json={"success": True})
        if request.url.path.endswith("/panel/api/inbounds/onlines"):
            return _ok(["u1", "u2"])
        return _fail("unexpected", status=404)

    client = _make_client(handler)
    try:
        emails = await client.online_emails()
    finally:
        await client.aclose()

    assert sorted(emails) == ["u1", "u2"]
