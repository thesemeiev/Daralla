from unittest.mock import AsyncMock

import pytest

from daralla_backend.services.xui_service import X3


class _FakeResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


class _FakeAsyncClient:
    def __init__(self, response: _FakeResponse):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str):
        return self._response


def _make_x3_for_subscription_links() -> X3:
    x3 = X3.__new__(X3)
    x3.host = "https://panel.example.com/panel"
    x3.vpn_host = "vpn.example.com"
    x3.subscription_port = 2096
    x3.subscription_url = None
    x3._ensure_login = AsyncMock(return_value=None)
    x3.list = AsyncMock(return_value={"success": True, "obj": []})
    return x3


def test_subscription_clash_base_urls_prefers_3x_ui_sub_clash_append():
    x3 = X3.__new__(X3)
    x3.subscription_url = "https://141.98.7.234:2096/daralla/sub"
    urls = x3._subscription_clash_base_urls()
    assert urls[0] == "https://141.98.7.234:2096/daralla/sub/clash"
    assert "https://141.98.7.234:2096/daralla/clash" in urls


def test_subscription_clash_base_urls_without_custom_sub_path():
    x3 = _make_x3_for_subscription_links()
    urls = x3._subscription_clash_base_urls()
    assert urls[0] == "https://vpn.example.com:2096/sub/clash"
    assert "https://vpn.example.com:2096/clash" in urls


@pytest.mark.asyncio
async def test_get_clash_subscription_yaml_uses_sub_clash_without_legacy_retry(monkeypatch):
    yaml_body = "proxies:\n  - name: n1\n    type: vless\n    server: h\n"
    calls: list[str] = []

    class _RoutingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url: str):
            calls.append(url)
            if "/sub/clash/" in url:
                return _FakeResponse(200, yaml_body)
            return _FakeResponse(404, "404 page not found")

    x3 = _make_x3_for_subscription_links()
    x3.subscription_url = "https://panel.example.com:2096/daralla/sub"
    x3._lookup_panel_sub_id = AsyncMock(return_value=None)

    monkeypatch.setattr(
        "daralla_backend.services.xui_service.httpx.AsyncClient",
        lambda **kwargs: _RoutingClient(),
    )

    body = await x3.get_clash_subscription_yaml(
        "user@example.com",
        subscription_token="panel-sub-token",
    )

    assert body == yaml_body.strip()
    assert calls == [
        "https://panel.example.com:2096/daralla/sub/clash/panel-sub-token",
    ]


@pytest.mark.asyncio
async def test_get_clash_subscription_yaml_falls_back_to_legacy_clash_path(monkeypatch):
    yaml_body = "proxies:\n  - name: n1\n    type: vless\n    server: h\n"
    calls: list[str] = []

    class _RoutingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url: str):
            calls.append(url)
            if "/sub/clash/" in url:
                return _FakeResponse(404, "404 page not found")
            if "/daralla/clash/" in url:
                return _FakeResponse(200, yaml_body)
            return _FakeResponse(404, "404 page not found")

    x3 = _make_x3_for_subscription_links()
    x3.subscription_url = "https://panel.example.com:2096/daralla/sub"
    x3._lookup_panel_sub_id = AsyncMock(return_value=None)

    monkeypatch.setattr(
        "daralla_backend.services.xui_service.httpx.AsyncClient",
        lambda **kwargs: _RoutingClient(),
    )

    body = await x3.get_clash_subscription_yaml(
        "user@example.com",
        subscription_token="panel-sub-token",
    )

    assert body == yaml_body.strip()
    assert calls == [
        "https://panel.example.com:2096/daralla/sub/clash/panel-sub-token",
        "https://panel.example.com:2096/daralla/clash/panel-sub-token",
    ]


@pytest.mark.asyncio
async def test_resolve_subscription_sub_id_prefers_panel_sub_id():
    x3 = _make_x3_for_subscription_links()
    x3._lookup_panel_sub_id = AsyncMock(return_value="panel-uuid-sub")
    sub_id = await x3._resolve_subscription_sub_id(
        "user@example.com",
        subscription_token="daralla-token",
    )
    assert sub_id == "panel-uuid-sub"


@pytest.mark.asyncio
async def test_get_subscription_links_accepts_hysteria2_and_tuic(monkeypatch):
    payload = "\n".join(
        [
            "hysteria2://pass@host:443?sni=example.com#Node-1",
            "tuic://uuid:pass@host:443?congestion_control=bbr#Node-2",
        ]
    )
    x3 = _make_x3_for_subscription_links()
    monkeypatch.setattr(
        "daralla_backend.services.xui_service.httpx.AsyncClient",
        lambda **kwargs: _FakeAsyncClient(_FakeResponse(200, payload)),
    )

    links = await x3.get_subscription_links(
        "user@example.com", subscription_token="sub-token-1",
    )

    assert links == [
        "hysteria2://pass@host:443?sni=example.com#Node-1",
        "tuic://uuid:pass@host:443?congestion_control=bbr#Node-2",
    ]


@pytest.mark.asyncio
async def test_get_subscription_links_keeps_mixed_protocols_and_skips_garbage(monkeypatch):
    payload = "\n".join(
        [
            "# comment",
            "vless://uuid@host:443?encryption=none#OldName",
            "not-a-link",
            "hysteria2://pass@hy.example:8443?alpn=h3#Hy",
            "trojan://secret@tr.example:443?sni=tr.example#Tr",
        ]
    )
    x3 = _make_x3_for_subscription_links()
    monkeypatch.setattr(
        "daralla_backend.services.xui_service.httpx.AsyncClient",
        lambda **kwargs: _FakeAsyncClient(_FakeResponse(200, payload)),
    )

    links = await x3.get_subscription_links(
        "user@example.com", server_name="Unified", subscription_token="sub-token-1",
    )

    assert links == [
        "vless://uuid@host:443?encryption=none#Unified",
        "hysteria2://pass@hy.example:8443?alpn=h3#Unified",
        "trojan://secret@tr.example:443?sni=tr.example#Unified",
    ]
