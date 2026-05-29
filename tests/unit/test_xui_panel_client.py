"""Unit tests for the standalone XUiPanelClient (no py3xui)."""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Dict, List, Optional

import httpx
import pytest

from daralla_backend.services.xui_panel_client import XUiPanelClient, XUiPanelError


class _Recorder:
    """Captures the HTTP requests sent through MockTransport."""

    def __init__(self) -> None:
        self.requests: List[httpx.Request] = []
        self.bodies: List[Optional[Dict[str, Any]]] = []


async def _make_client(
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
    st = client._loop_http_state()
    st.client = httpx.AsyncClient(transport=transport, timeout=client._timeout)
    st.login_lock = asyncio.Lock()
    return client


def _ok(payload: Any = None) -> httpx.Response:
    body: Dict[str, Any] = {"success": True}
    if payload is not None:
        body["obj"] = payload
    return httpx.Response(200, json=body)


def _fail(msg: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json={"success": False, "msg": msg})


@pytest.mark.asyncio
async def test_per_event_loop_has_isolated_httpx_client():
    """Quart (отдельный поток + asyncio.run) и бот не должны шарить один AsyncClient."""
    client = XUiPanelClient(
        host="https://panel.example.com:2053/secret",
        login="admin",
        password="pw",
        verify_tls=False,
    )
    st_main = client._loop_http_state()
    await client._ensure_http_client(st_main)
    assert st_main.client is not None
    main_client_id = id(st_main.client)

    other_ids: List[int] = []

    def run_in_thread() -> None:
        async def inner() -> None:
            st = client._loop_http_state()
            await client._ensure_http_client(st)
            assert st.client is not None
            other_ids.append(id(st.client))
            await client.aclose()

        asyncio.run(inner())

    t = threading.Thread(target=run_in_thread)
    t.start()
    t.join()
    assert len(other_ids) == 1
    assert other_ids[0] != main_client_id
    await client.aclose()


@pytest.mark.asyncio
async def test_login_then_list_inbounds_calls_correct_paths():
    rec = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        rec.requests.append(request)
        if request.url.path.endswith("/csrf-token"):
            return httpx.Response(404)
        if request.url.path.endswith("/login"):
            return httpx.Response(200, json={"success": True})
        if request.url.path.endswith("/panel/api/inbounds/list"):
            return _ok([{"id": 1, "protocol": "vless"}])
        return httpx.Response(404, json={"success": False, "msg": "nope"})

    client = await _make_client(handler)
    try:
        inbounds = await client.list_inbounds()
    finally:
        await client.aclose()

    assert inbounds == [{"id": 1, "protocol": "vless"}]
    paths = [r.url.path for r in rec.requests]
    assert paths[0].endswith("/csrf-token")
    assert paths[1].endswith("/login")
    assert paths[2].endswith("/panel/api/inbounds/list")


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

    client = await _make_client(handler)
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
    client = await _make_client(handler)
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

    client = await _make_client(handler)
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

    client = await _make_client(handler)
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
        if request.url.path.endswith("/csrf-token"):
            return httpx.Response(404)
        if request.url.path.endswith("/login"):
            state["logins"] += 1
            return httpx.Response(200, json={"success": True})
        state["calls"] += 1
        if state["calls"] == 1:
            return httpx.Response(401, json={"success": False, "msg": "session expired"})
        return _ok([])

    client = await _make_client(handler, max_retries=3)
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

    client = await _make_client(handler)
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

    client = await _make_client(handler)
    try:
        with pytest.raises(XUiPanelError) as ei:
            await client.list_inbounds()
    finally:
        await client.aclose()

    assert "bad credentials" in str(ei.value)


@pytest.mark.asyncio
async def test_login_with_csrf_token_v3_panel():
    rec = _Recorder()
    csrf = "csrf-test-token-abc"

    def handler(request: httpx.Request) -> httpx.Response:
        rec.requests.append(request)
        path = request.url.path
        if path.endswith("/csrf-token"):
            return httpx.Response(200, json={"success": True, "obj": csrf})
        if path.endswith("/login"):
            assert request.headers.get("X-CSRF-Token") == csrf
            return httpx.Response(200, json={"success": True})
        if path.endswith("/panel/api/inbounds/list"):
            return _ok([{"id": 1, "protocol": "vless"}])
        return _fail("unexpected", status=404)

    client = await _make_client(handler)
    try:
        inbounds = await client.list_inbounds()
    finally:
        await client.aclose()

    assert inbounds == [{"id": 1, "protocol": "vless"}]
    paths = [r.url.path for r in rec.requests]
    assert paths[0].endswith("/csrf-token")
    assert paths[1].endswith("/login")
    assert paths[2].endswith("/panel/api/inbounds/list")


@pytest.mark.asyncio
async def test_post_api_includes_csrf_after_login():
    rec = _Recorder()
    csrf = "csrf-for-post"

    def handler(request: httpx.Request) -> httpx.Response:
        rec.requests.append(request)
        path = request.url.path
        if path.endswith("/csrf-token"):
            return httpx.Response(200, json={"success": True, "obj": csrf})
        if path.endswith("/login"):
            return httpx.Response(200, json={"success": True})
        if path.endswith("/panel/api/clients/add"):
            assert request.headers.get("X-CSRF-Token") == csrf
            body = json.loads(request.content.decode())
            assert body["inboundIds"] == [3]
            assert body["client"]["email"] == "u1"
            assert "protocol" not in body["client"]
            return _ok()
        return _fail("unexpected", status=404)

    client = await _make_client(handler)
    try:
        await client.add_client(
            3, {"email": "u1", "id": "uuid", "protocol": "vless"}
        )
    finally:
        await client.aclose()

    post_reqs = [r for r in rec.requests if r.method == "POST" and "/clients/add" in r.url.path]
    assert len(post_reqs) == 1
    assert post_reqs[0].headers.get("X-CSRF-Token") == csrf


@pytest.mark.asyncio
async def test_legacy_panel_without_csrf_endpoint_still_works():
    rec = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        rec.requests.append(request)
        path = request.url.path
        if path.endswith("/csrf-token"):
            return httpx.Response(404)
        if path.endswith("/login"):
            assert request.headers.get("X-CSRF-Token") is None
            return httpx.Response(200, json={"success": True})
        if path.endswith("/panel/api/inbounds/list"):
            return _ok([])
        return _fail("unexpected", status=404)

    client = await _make_client(handler)
    try:
        result = await client.list_inbounds()
    finally:
        await client.aclose()

    assert result == []
    paths = [r.url.path for r in rec.requests]
    assert paths[0].endswith("/csrf-token")
    assert paths[1].endswith("/login")


@pytest.mark.asyncio
async def test_bearer_api_token_skips_login_and_csrf():
    rec = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        rec.requests.append(request)
        path = request.url.path
        if path.endswith("/login") or path.endswith("/csrf-token"):
            return _fail("should not login", status=500)
        if path.endswith("/panel/api/inbounds/list"):
            assert request.headers.get("Authorization") == "Bearer panel-api-token"
            assert request.headers.get("X-CSRF-Token") is None
            return _ok([{"id": 2}])
        return _fail("unexpected", status=404)

    client = XUiPanelClient(
        host="https://panel.example.com:2053/secret",
        login="admin",
        password="pw",
        verify_tls=False,
        api_token="panel-api-token",
    )
    transport = httpx.MockTransport(handler)
    st = client._loop_http_state()
    st.client = httpx.AsyncClient(transport=transport, timeout=client._timeout)
    st.login_lock = asyncio.Lock()
    try:
        inbounds = await client.list_inbounds()
    finally:
        await client.aclose()

    assert inbounds == [{"id": 2}]
    assert not any(r.url.path.endswith("/login") for r in rec.requests)


@pytest.mark.asyncio
async def test_online_emails_returns_list():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/login"):
            return httpx.Response(200, json={"success": True})
        if request.url.path.endswith("/csrf-token"):
            return httpx.Response(404)
        if request.url.path.endswith("/panel/api/inbounds/onlines"):
            return _ok(["u1", "u2"])
        return _fail("unexpected", status=404)

    client = await _make_client(handler)
    try:
        emails = await client.online_emails()
    finally:
        await client.aclose()

    assert sorted(emails) == ["u1", "u2"]


@pytest.mark.asyncio
async def test_v3_online_emails_uses_clients_onlines():
    csrf = "csrf-onlines"

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/csrf-token"):
            return httpx.Response(200, json={"success": True, "obj": csrf})
        if path.endswith("/login"):
            return httpx.Response(200, json={"success": True})
        if path.endswith("/panel/api/clients/onlines"):
            assert request.headers.get("X-CSRF-Token") == csrf
            return _ok(["ee@x", "fi@x"])
        if path.endswith("/panel/api/inbounds/onlines"):
            return _fail("legacy onlines should not be called", status=404)
        return _fail("unexpected", status=404)

    client = await _make_client(handler)
    try:
        emails = await client.online_emails()
    finally:
        await client.aclose()

    assert sorted(emails) == ["ee@x", "fi@x"]


@pytest.mark.asyncio
async def test_v3_update_and_delete_client_by_email():
    csrf = "csrf-crud"
    rec = _Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        rec.requests.append(request)
        path = request.url.path
        if path.endswith("/csrf-token"):
            return httpx.Response(200, json={"success": True, "obj": csrf})
        if path.endswith("/login"):
            return httpx.Response(200, json={"success": True})
        if "/panel/api/clients/update/" in path:
            body = json.loads(request.content.decode())
            assert body["email"] == "user@example.com"
            assert body["enable"] is True
            return _ok()
        if "/panel/api/clients/del/" in path:
            return _ok()
        if "/panel/api/clients/traffic/" in path:
            return _ok({"up": 1, "down": 2, "total": 0})
        return _fail("unexpected", status=404)

    client = await _make_client(handler)
    try:
        await client.update_client(
            client_url_id="uuid-id",
            inbound_id=5,
            client_payload={"email": "user@example.com", "enable": True, "protocol": "vless"},
        )
        await client.delete_client_by_email(5, "user@example.com")
        traffic = await client.get_client_traffics_by_email("user@example.com")
    finally:
        await client.aclose()

    assert traffic == {"up": 1, "down": 2, "total": 0}
    paths = [r.url.path for r in rec.requests]
    assert any("/panel/api/clients/update/" in p for p in paths)
    assert any("/panel/api/clients/del/" in p for p in paths)
    assert any("/panel/api/clients/traffic/" in p for p in paths)
