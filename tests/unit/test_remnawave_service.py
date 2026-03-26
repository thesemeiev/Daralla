import pytest

from bot.services.remnawave_service import RemnaWaveService


@pytest.mark.asyncio
async def test_ensure_active_access_uses_template_and_persists_binding(monkeypatch):
    service = RemnaWaveService()
    service.api_url = ""
    service.api_key = ""
    service.link_template = "https://vpn.example/sub/{token}"

    async def fake_get_binding(subscription_id):
        _ = subscription_id
        return None

    captured = {}

    async def fake_upsert_binding(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr("bot.services.remnawave_service.get_binding_by_subscription", fake_get_binding)
    monkeypatch.setattr("bot.services.remnawave_service.upsert_binding", fake_upsert_binding)

    ok = await service.ensure_active_access(
        subscription_id=10,
        user_id="u-1",
        token="abc",
        expires_at=123,
        device_limit=1,
    )

    assert ok is True
    assert captured["subscription_id"] == 10
    assert captured["subscription_url"] == "https://vpn.example/sub/abc"


@pytest.mark.asyncio
async def test_suspend_access_calls_panel_when_binding_exists(monkeypatch):
    service = RemnaWaveService()
    service.api_url = "https://panel.example"
    service.api_key = "k"

    async def fake_get_binding(subscription_id):
        _ = subscription_id
        return {"panel_user_id": "panel-42"}

    called = {}

    async def fake_post(path, payload):
        called["path"] = path
        called["payload"] = payload
        return {}

    monkeypatch.setattr("bot.services.remnawave_service.get_binding_by_subscription", fake_get_binding)
    monkeypatch.setattr(service, "_post", fake_post)

    ok = await service.suspend_access(subscription_id=42)
    assert ok is True
    assert called["path"] == "/api/integration/subscription/suspend"
    assert called["payload"]["panel_user_id"] == "panel-42"


@pytest.mark.asyncio
async def test_get_subscription_link_falls_back_to_template(monkeypatch):
    service = RemnaWaveService()
    service.api_url = ""
    service.api_key = ""
    service.link_template = "https://fallback/sub/{token}"

    async def fake_get_binding(subscription_id):
        _ = subscription_id
        return None

    monkeypatch.setattr("bot.services.remnawave_service.get_binding_by_subscription", fake_get_binding)

    link = await service.get_subscription_link(subscription_id=7, token="ttt")
    assert link == "https://fallback/sub/ttt"


@pytest.mark.asyncio
async def test_get_usage_returns_zero_without_binding(monkeypatch):
    service = RemnaWaveService()

    async def fake_get_binding(subscription_id):
        _ = subscription_id
        return None

    monkeypatch.setattr("bot.services.remnawave_service.get_binding_by_subscription", fake_get_binding)
    usage = await service.get_usage(subscription_id=1)
    assert usage == {"upload": 0, "download": 0, "total": 0}
