"""Удаление пакетов трафика подписки."""

import time
import uuid

import pytest

from daralla_backend.db.users_db import get_or_create_subscriber
from daralla_backend.db.subscriptions_db import (
    create_subscription,
    create_subscription_traffic_bucket,
    delete_subscription_traffic_bucket,
    ensure_default_unlimited_bucket,
    get_subscription_server_bucket_map,
    get_subscription_traffic_bucket,
    list_subscription_traffic_buckets,
    set_subscription_server_bucket,
)


@pytest.mark.asyncio
async def test_delete_limited_bucket_reassigns_servers(db):
    suffix = uuid.uuid4().hex[:8]
    subscriber_id = await get_or_create_subscriber(f"u_del_{suffix}")
    now = int(time.time())
    sub_id, _ = await create_subscription(
        subscriber_id=subscriber_id,
        period="month",
        device_limit=1,
        price=1.0,
        expires_at=now + 86400 * 30,
        group_id=None,
    )
    default_id = await ensure_default_unlimited_bucket(sub_id)
    limited_id = await create_subscription_traffic_bucket(
        sub_id,
        f"lim_{suffix}",
        limit_bytes=1024**3,
        is_unlimited=False,
    )
    await set_subscription_server_bucket(sub_id, f"srv_{suffix}", limited_id)

    ok, err = await delete_subscription_traffic_bucket(sub_id, limited_id)
    assert ok is True
    assert err is None

    assert await get_subscription_traffic_bucket(limited_id) is None
    buckets = await list_subscription_traffic_buckets(sub_id)
    assert len(buckets) == 1
    mapping = await get_subscription_server_bucket_map(sub_id)
    assert mapping.get(f"srv_{suffix}") == default_id


@pytest.mark.asyncio
async def test_cannot_delete_unlimited_bucket(db):
    suffix = uuid.uuid4().hex[:8]
    subscriber_id = await get_or_create_subscriber(f"u_pu_{suffix}")
    now = int(time.time())
    sub_id, _ = await create_subscription(
        subscriber_id=subscriber_id,
        period="month",
        device_limit=1,
        price=1.0,
        expires_at=now + 86400 * 30,
        group_id=None,
    )
    default_id = await ensure_default_unlimited_bucket(sub_id)
    await create_subscription_traffic_bucket(sub_id, f"lim_{suffix}", limit_bytes=1024, is_unlimited=False)

    ok, err = await delete_subscription_traffic_bucket(sub_id, default_id)
    assert ok is False
    assert err == "protected_unlimited"


@pytest.mark.asyncio
async def test_cannot_delete_last_bucket(db):
    """Единственный пакет (лимитированный, без отдельного безлимита) удалять нельзя."""
    suffix = uuid.uuid4().hex[:8]
    subscriber_id = await get_or_create_subscriber(f"u_lb_{suffix}")
    now = int(time.time())
    sub_id, _ = await create_subscription(
        subscriber_id=subscriber_id,
        period="month",
        device_limit=1,
        price=1.0,
        expires_at=now + 86400 * 30,
        group_id=None,
    )
    limited_only_id = await create_subscription_traffic_bucket(
        sub_id,
        f"only_lim_{suffix}",
        limit_bytes=1024,
        is_unlimited=False,
    )

    ok, err = await delete_subscription_traffic_bucket(sub_id, limited_only_id)
    assert ok is False
    assert err == "last_bucket"
