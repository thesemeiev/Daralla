"""Интеграционные тесты периодной квоты трафика и аллокации дельты."""

import time
import uuid

import pytest

from daralla_backend.db.subscriptions_db import (
    allocate_subscription_traffic_quota_delta,
    create_subscription,
    create_subscription_traffic_bucket,
    ensure_default_unlimited_bucket,
    upsert_subscription_traffic_quota_row,
)
from daralla_backend.db.users_db import get_or_create_subscriber
from daralla_backend.services import traffic_quota_period_service as tq_mod
from daralla_backend.services.traffic_quota_period_service import reset_included_quota_after_payment


@pytest.mark.asyncio
async def test_allocate_quota_delta_only_included(db, monkeypatch):
    monkeypatch.setenv("DARALLA_TRAFFIC_BUCKETS_ENABLED", "1")
    suffix = uuid.uuid4().hex[:8]
    subscriber_id = await get_or_create_subscriber(f"u_tq_{suffix}")
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
    bid = await create_subscription_traffic_bucket(
        sub_id,
        f"lim_{suffix}",
        limit_bytes=10 * 1024**3,
        is_unlimited=False,
    )
    await upsert_subscription_traffic_quota_row(
        sub_id,
        bid,
        included_allowance_bytes=1000,
        included_used_bytes=100,
        purchased_remaining_bytes=500,
    )

    await allocate_subscription_traffic_quota_delta(sub_id, bid, 200)
    from daralla_backend.db.subscriptions_db import get_subscription_traffic_quota

    row = await get_subscription_traffic_quota(sub_id)
    assert row is not None
    assert int(row["included_used_bytes"]) == 300
    assert int(row["purchased_remaining_bytes"]) == 500


@pytest.mark.asyncio
async def test_allocate_quota_delta_spills_to_purchased(db, monkeypatch):
    monkeypatch.setenv("DARALLA_TRAFFIC_BUCKETS_ENABLED", "1")
    suffix = uuid.uuid4().hex[:8]
    subscriber_id = await get_or_create_subscriber(f"u_tq2_{suffix}")
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
    bid = await create_subscription_traffic_bucket(
        sub_id,
        f"lim2_{suffix}",
        limit_bytes=10 * 1024**3,
        is_unlimited=False,
    )
    await upsert_subscription_traffic_quota_row(
        sub_id,
        bid,
        included_allowance_bytes=1000,
        included_used_bytes=900,
        purchased_remaining_bytes=500,
    )

    await allocate_subscription_traffic_quota_delta(sub_id, bid, 200)
    from daralla_backend.db.subscriptions_db import get_subscription_traffic_quota

    row = await get_subscription_traffic_quota(sub_id)
    assert int(row["included_used_bytes"]) == 1000
    assert int(row["purchased_remaining_bytes"]) == 400


@pytest.mark.asyncio
async def test_reset_included_quota_after_payment_keeps_purchased(db, monkeypatch):
    monkeypatch.setenv("DARALLA_TRAFFIC_BUCKETS_ENABLED", "1")
    suffix = uuid.uuid4().hex[:8]
    subscriber_id = await get_or_create_subscriber(f"u_tqr_{suffix}")
    now = int(time.time())
    sub_id, _ = await create_subscription(
        subscriber_id=subscriber_id,
        period="month",
        device_limit=1,
        price=1.0,
        expires_at=now + 86400 * 30,
        group_id=None,
    )
    bid = await create_subscription_traffic_bucket(
        sub_id,
        f"limr_{suffix}",
        limit_bytes=1024**3,
        is_unlimited=False,
    )
    await upsert_subscription_traffic_quota_row(
        sub_id,
        bid,
        included_allowance_bytes=100,
        included_used_bytes=77,
        purchased_remaining_bytes=999,
        bump_period_version=False,
    )

    async def fake_resolve(_sid: int, _gid: int):
        return bid, int(1024**3)

    real_get_only = tq_mod.get_subscription_by_id_only

    async def sub_with_group(sid: int):
        row = await real_get_only(sid)
        if row and int(row.get("id") or 0) == int(sid):
            d = dict(row)
            d["group_id"] = 42
            return d
        return row

    monkeypatch.setattr(
        "daralla_backend.services.traffic_quota_period_service._resolve_group_limited_bucket_id",
        fake_resolve,
    )
    monkeypatch.setattr(
        "daralla_backend.services.traffic_quota_period_service.get_subscription_by_id_only",
        sub_with_group,
    )

    await reset_included_quota_after_payment(sub_id, paid_period_key="3month", payment_days=90)

    from daralla_backend.db.subscriptions_db import get_subscription_traffic_quota

    row = await get_subscription_traffic_quota(sub_id)
    assert int(row["included_used_bytes"]) == 0
    assert int(row["purchased_remaining_bytes"]) == 999
    assert int(row["included_allowance_bytes"]) == 3 * int(1024**3)
    assert int(row["traffic_period_version"]) >= 1
