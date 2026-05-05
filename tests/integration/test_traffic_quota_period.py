"""Интеграционные тесты периодной квоты трафика и аллокации дельты."""

import time
import uuid
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest

from daralla_backend.db import DB_PATH
from daralla_backend.db.subscriptions_db import (
    adjust_subscription_traffic_quota_for_bucket_usage,
    allocate_subscription_traffic_quota_delta,
    apply_bucket_usage_adjustment,
    create_subscription,
    create_subscription_traffic_bucket,
    ensure_default_unlimited_bucket,
    get_subscription_traffic_quota,
    set_subscription_server_bucket,
    subscription_should_show_user_traffic_quota,
    upsert_subscription_traffic_quota_row,
)
from daralla_backend.db.users_db import get_or_create_subscriber
from daralla_backend.services import traffic_quota_period_service as tq_mod
from daralla_backend.services.traffic_quota_period_service import (
    current_month_start_unix,
    reset_included_quota_calendar,
)


async def _clear_subscription_group_id(subscription_id: int) -> None:
    """create_subscription(group_id=None) всё равно резолвит группу через resolve_group_id; для сценария «без группы» обнуляем в БД."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE subscriptions SET group_id = NULL WHERE id = ?",
            (int(subscription_id),),
        )
        await conn.commit()


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

    row = await get_subscription_traffic_quota(sub_id)
    assert int(row["included_used_bytes"]) == 1000
    assert int(row["purchased_remaining_bytes"]) == 400


@pytest.mark.asyncio
async def test_reset_included_quota_calendar_keeps_purchased(db, monkeypatch):
    monkeypatch.setenv("DARALLA_TRAFFIC_BUCKETS_ENABLED", "1")
    svc = MagicMock()
    svc.enqueue_enforcement_if_needed = AsyncMock(return_value=0)
    monkeypatch.setattr(
        "daralla_backend.services.traffic_bucket_service.get_traffic_bucket_service",
        lambda: svc,
    )
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
        period_started_at=0,
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

    ms = current_month_start_unix()
    assert await reset_included_quota_calendar(sub_id, month_start_utc=ms) is True

    row = await get_subscription_traffic_quota(sub_id)
    assert int(row["included_used_bytes"]) == 0
    assert int(row["purchased_remaining_bytes"]) == 999
    assert int(row["included_allowance_bytes"]) == int(1024**3)
    assert int(row["traffic_period_version"]) >= 1
    assert int(row["period_started_at"]) == ms


@pytest.mark.asyncio
async def test_quota_ui_hidden_when_only_unlimited_buckets_mapped(db, monkeypatch):
    monkeypatch.setenv("DARALLA_TRAFFIC_BUCKETS_ENABLED", "1")
    suffix = uuid.uuid4().hex[:8]
    subscriber_id = await get_or_create_subscriber(f"u_tqmap_{suffix}")
    now = int(time.time())
    sub_id, _ = await create_subscription(
        subscriber_id=subscriber_id,
        period="month",
        device_limit=1,
        price=1.0,
        expires_at=now + 86400 * 30,
        group_id=None,
    )
    def_id = await ensure_default_unlimited_bucket(sub_id)
    lim_id = await create_subscription_traffic_bucket(
        sub_id,
        f"lim_map_{suffix}",
        limit_bytes=1024**3,
        is_unlimited=False,
    )
    await upsert_subscription_traffic_quota_row(
        sub_id,
        lim_id,
        included_allowance_bytes=100,
        included_used_bytes=0,
        purchased_remaining_bytes=0,
    )
    await set_subscription_server_bucket(sub_id, "srv-x", def_id)

    q = await get_subscription_traffic_quota(sub_id)
    assert q is not None
    assert await subscription_should_show_user_traffic_quota(sub_id, dict(q)) is False

    await set_subscription_server_bucket(sub_id, "srv-y", lim_id)
    assert await subscription_should_show_user_traffic_quota(sub_id, dict(q)) is True


@pytest.mark.asyncio
async def test_quota_ui_true_when_metered_quota_no_mapping_yet(db, monkeypatch):
    monkeypatch.setenv("DARALLA_TRAFFIC_BUCKETS_ENABLED", "1")
    suffix = uuid.uuid4().hex[:8]
    subscriber_id = await get_or_create_subscriber(f"u_tqnomap_{suffix}")
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
    lim_id = await create_subscription_traffic_bucket(
        sub_id,
        f"lim_nom_{suffix}",
        limit_bytes=1024**3,
        is_unlimited=False,
    )
    await upsert_subscription_traffic_quota_row(
        sub_id,
        lim_id,
        included_allowance_bytes=50,
        included_used_bytes=0,
        purchased_remaining_bytes=0,
    )

    q = await get_subscription_traffic_quota(sub_id)
    assert await subscription_should_show_user_traffic_quota(sub_id, dict(q)) is True


@pytest.mark.asyncio
async def test_quota_ui_false_when_quota_points_at_unlimited_bucket_no_mapping(db, monkeypatch):
    monkeypatch.setenv("DARALLA_TRAFFIC_BUCKETS_ENABLED", "1")
    suffix = uuid.uuid4().hex[:8]
    subscriber_id = await get_or_create_subscriber(f"u_tqunlim_{suffix}")
    now = int(time.time())
    sub_id, _ = await create_subscription(
        subscriber_id=subscriber_id,
        period="month",
        device_limit=1,
        price=1.0,
        expires_at=now + 86400 * 30,
        group_id=None,
    )
    def_id = await ensure_default_unlimited_bucket(sub_id)
    await upsert_subscription_traffic_quota_row(
        sub_id,
        def_id,
        included_allowance_bytes=10,
        included_used_bytes=0,
        purchased_remaining_bytes=0,
    )

    q = await get_subscription_traffic_quota(sub_id)
    assert await subscription_should_show_user_traffic_quota(sub_id, dict(q)) is False


@pytest.mark.asyncio
async def test_quota_adjust_positive_syncs_with_bucket_adjust(db, monkeypatch):
    monkeypatch.setenv("DARALLA_TRAFFIC_BUCKETS_ENABLED", "1")
    suffix = uuid.uuid4().hex[:8]
    subscriber_id = await get_or_create_subscriber(f"u_tqadj_{suffix}")
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
        f"lim_adj_{suffix}",
        limit_bytes=10 * 1024**3,
        is_unlimited=False,
    )
    await upsert_subscription_traffic_quota_row(
        sub_id,
        bid,
        included_allowance_bytes=1000,
        included_used_bytes=100,
        purchased_remaining_bytes=400,
    )
    delta = 50
    await apply_bucket_usage_adjustment(bid, delta, reason="test")
    await adjust_subscription_traffic_quota_for_bucket_usage(sub_id, bid, delta)

    row = await get_subscription_traffic_quota(sub_id)
    assert int(row["included_used_bytes"]) == 150
    assert int(row["purchased_remaining_bytes"]) == 400


@pytest.mark.asyncio
async def test_quota_adjust_negative_returns_to_purchased(db, monkeypatch):
    monkeypatch.setenv("DARALLA_TRAFFIC_BUCKETS_ENABLED", "1")
    suffix = uuid.uuid4().hex[:8]
    subscriber_id = await get_or_create_subscriber(f"u_tqadjn_{suffix}")
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
        f"lim_adjn_{suffix}",
        limit_bytes=10 * 1024**3,
        is_unlimited=False,
    )
    await upsert_subscription_traffic_quota_row(
        sub_id,
        bid,
        included_allowance_bytes=1000,
        included_used_bytes=80,
        purchased_remaining_bytes=10,
    )
    await adjust_subscription_traffic_quota_for_bucket_usage(sub_id, bid, -50)

    row = await get_subscription_traffic_quota(sub_id)
    assert int(row["included_used_bytes"]) == 30
    assert int(row["purchased_remaining_bytes"]) == 10

    await adjust_subscription_traffic_quota_for_bucket_usage(sub_id, bid, -50)
    row = await get_subscription_traffic_quota(sub_id)
    assert int(row["included_used_bytes"]) == 0
    # 30 байт снято с included_used, оставшиеся 20 из дельты возвращаются в докупку: 10 + 20 = 30
    assert int(row["purchased_remaining_bytes"]) == 30


@pytest.mark.asyncio
async def test_reset_included_quota_calendar_without_group_uses_bucket_limit(db, monkeypatch):
    monkeypatch.setenv("DARALLA_TRAFFIC_BUCKETS_ENABLED", "1")
    svc = MagicMock()
    svc.enqueue_enforcement_if_needed = AsyncMock(return_value=0)
    monkeypatch.setattr(
        "daralla_backend.services.traffic_bucket_service.get_traffic_bucket_service",
        lambda: svc,
    )
    suffix = uuid.uuid4().hex[:8]
    subscriber_id = await get_or_create_subscriber(f"u_tqnogrp_{suffix}")
    now = int(time.time())
    sub_id, _ = await create_subscription(
        subscriber_id=subscriber_id,
        period="month",
        device_limit=1,
        price=1.0,
        expires_at=now + 86400 * 30,
        group_id=None,
    )
    await _clear_subscription_group_id(sub_id)
    bid = await create_subscription_traffic_bucket(
        sub_id,
        f"lim_ngrp_{suffix}",
        limit_bytes=int(1024**3),
        is_unlimited=False,
    )
    await upsert_subscription_traffic_quota_row(
        sub_id,
        bid,
        included_allowance_bytes=int(1024**3),
        included_used_bytes=500,
        purchased_remaining_bytes=100,
        bump_period_version=False,
        period_started_at=0,
    )
    ms = current_month_start_unix()
    assert await reset_included_quota_calendar(sub_id, month_start_utc=ms) is True

    row = await get_subscription_traffic_quota(sub_id)
    assert int(row["included_used_bytes"]) == 0
    assert int(row["purchased_remaining_bytes"]) == 100
    assert int(row["included_allowance_bytes"]) == int(1024**3)
    assert int(row["traffic_period_version"]) >= 1
