"""Валидация admin payload для назначения нод и обновления пакетов трафика."""

import time
import uuid
from unittest.mock import AsyncMock

import pytest

from daralla_backend.db.subscriptions_db import (
    add_subscription_server,
    create_subscription,
    create_subscription_traffic_bucket,
    ensure_default_unlimited_bucket,
)
from daralla_backend.db.users_db import get_or_create_subscriber
from daralla_backend.services import admin_subscriptions_flow_service as flow


@pytest.mark.asyncio
async def test_assign_servers_unknown_node_returns_400(db, monkeypatch):
    suffix = uuid.uuid4().hex[:8]
    subscriber_id = await get_or_create_subscriber(f"u_as_{suffix}")
    now = int(time.time())
    sub_id, _ = await create_subscription(
        subscriber_id=subscriber_id,
        period="month",
        device_limit=1,
        price=1.0,
        expires_at=now + 86400 * 30,
        group_id=None,
    )
    await ensure_default_unlimited_bucket(sub_id)
    limited_id = await create_subscription_traffic_bucket(
        sub_id,
        f"lim_{suffix}",
        limit_bytes=1024**3,
        is_unlimited=False,
    )
    await add_subscription_server(sub_id, f"srv_ok_{suffix}", f"c_{suffix}", None)

    svc = AsyncMock()
    svc.enqueue_enforcement_if_needed = AsyncMock()
    monkeypatch.setattr(flow, "get_traffic_bucket_service", lambda: svc)
    monkeypatch.setattr(flow, "_traffic_bucket_snapshot", AsyncMock(return_value={"buckets": [], "server_bucket_map": {}}))

    _, err, code = await flow.assign_subscription_servers_bucket_payload(
        sub_id,
        limited_id,
        [f"srv_bad_{suffix}"],
    )
    assert code == 400
    assert err and "не привязана" in err.get("error", "")


@pytest.mark.asyncio
async def test_update_bucket_window_days_zero_returns_400(db, monkeypatch):
    suffix = uuid.uuid4().hex[:8]
    subscriber_id = await get_or_create_subscriber(f"u_uw_{suffix}")
    now = int(time.time())
    sub_id, _ = await create_subscription(
        subscriber_id=subscriber_id,
        period="month",
        device_limit=1,
        price=1.0,
        expires_at=now + 86400 * 30,
        group_id=None,
    )
    await ensure_default_unlimited_bucket(sub_id)
    limited_id = await create_subscription_traffic_bucket(
        sub_id,
        f"lim_{suffix}",
        limit_bytes=1024**3,
        is_unlimited=False,
    )

    svc = AsyncMock()
    svc.enqueue_enforcement_if_needed = AsyncMock()
    monkeypatch.setattr(flow, "get_traffic_bucket_service", lambda: svc)

    _, err, code = await flow.update_subscription_traffic_bucket_payload(
        sub_id,
        limited_id,
        {"window_days": 0},
    )
    assert code == 400
    assert err and "Окно учёта" in err.get("error", "")


@pytest.mark.asyncio
async def test_update_limited_bucket_empty_name_returns_400(db, monkeypatch):
    suffix = uuid.uuid4().hex[:8]
    subscriber_id = await get_or_create_subscriber(f"u_nm_{suffix}")
    now = int(time.time())
    sub_id, _ = await create_subscription(
        subscriber_id=subscriber_id,
        period="month",
        device_limit=1,
        price=1.0,
        expires_at=now + 86400 * 30,
        group_id=None,
    )
    await ensure_default_unlimited_bucket(sub_id)
    limited_id = await create_subscription_traffic_bucket(
        sub_id,
        f"lim_{suffix}",
        limit_bytes=1024**3,
        is_unlimited=False,
    )

    svc = AsyncMock()
    svc.enqueue_enforcement_if_needed = AsyncMock()
    monkeypatch.setattr(flow, "get_traffic_bucket_service", lambda: svc)

    _, err, code = await flow.update_subscription_traffic_bucket_payload(
        sub_id,
        limited_id,
        {"name": "   "},
    )
    assert code == 400
    assert err and "название" in err.get("error", "").lower()
