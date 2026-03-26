import hashlib
import hmac
import json
import time

import pytest
from quart import Quart

from bot.web.app_quart import create_quart_app


def _sig(secret: str, payload: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


@pytest.fixture
def quart_app_with_routes():
    return create_quart_app(bot_app=object())


@pytest.mark.asyncio
async def test_yookassa_webhook_rejects_without_signature(monkeypatch, quart_app_with_routes: Quart):
    monkeypatch.setenv("YOOKASSA_WEBHOOK_SECRET", "sec")
    client = quart_app_with_routes.test_client()
    payload = {"object": {"id": "pay-sign-1", "status": "succeeded"}}
    response = await client.post("/webhook/yookassa", json=payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_yookassa_webhook_accepts_valid_signature(monkeypatch, quart_app_with_routes: Quart):
    monkeypatch.setenv("YOOKASSA_WEBHOOK_SECRET", "sec")
    monkeypatch.setenv("WEBHOOK_REPLAY_WINDOW_SECONDS", "300")
    client = quart_app_with_routes.test_client()
    body_obj = {"object": {"id": "pay-sign-2", "status": "succeeded"}}
    body = json.dumps(body_obj, separators=(",", ":")).encode("utf-8")
    ts = str(int(time.time()))
    signature = _sig("sec", body)
    response = await client.post(
        "/webhook/yookassa",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Yookassa-Signature": signature,
            "X-Yookassa-Timestamp": ts,
        },
    )
    assert response.status_code == 200
