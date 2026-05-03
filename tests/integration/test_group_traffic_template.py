"""Integration tests: server group traffic templates and materialization."""
import time
import uuid

import pytest

from daralla_backend.db import (
    add_server_config,
    add_server_group,
    create_subscription,
    create_subscription_traffic_bucket,
    get_or_create_subscriber,
    get_server_group_traffic_template,
    get_subscription_server_bucket_map,
    list_subscription_traffic_buckets,
    replace_server_group_traffic_limited_servers,
    upsert_server_group_traffic_template,
)
from daralla_backend.services.group_traffic_bucket_names import group_limited_bucket_stable_name
from daralla_backend.services.group_traffic_template_service import (
    apply_group_traffic_template_bulk,
    apply_template_to_subscription,
)


@pytest.mark.asyncio
async def test_group_traffic_template_db_roundtrip(db):
    suffix = uuid.uuid4().hex[:8]
    gid = await add_server_group(f"GTmpl_{suffix}", description="t", is_default=False)
    s1 = f"node_a_{suffix}"
    s2 = f"node_b_{suffix}"
    await add_server_config(gid, s1, "https://example.com", "u", "p")
    await add_server_config(gid, s2, "https://example.com", "u", "p")

    await upsert_server_group_traffic_template(
        gid,
        enabled=True,
        limited_bucket_name="Пакет EU",
        limit_bytes=5 * 1024 * 1024 * 1024,
        is_unlimited=False,
        window_days=30,
        credit_periods_total=2,
    )
    await replace_server_group_traffic_limited_servers(gid, [s1])

    row = await get_server_group_traffic_template(gid)
    assert row is not None
    assert int(row["enabled"]) == 1
    assert row["limited_bucket_name"] == "Пакет EU"
    assert int(row["limit_bytes"]) == 5 * 1024 * 1024 * 1024


@pytest.mark.asyncio
async def test_apply_template_creates_buckets_and_map(db, monkeypatch):
    monkeypatch.setenv("DARALLA_TRAFFIC_BUCKETS_ENABLED", "1")
    suffix = uuid.uuid4().hex[:8]
    gid = await add_server_group(f"GApply_{suffix}", description="t", is_default=False)
    s_lim = f"lim_{suffix}"
    s_free = f"free_{suffix}"
    await add_server_config(gid, s_lim, "https://example.com", "u", "p")
    await add_server_config(gid, s_free, "https://example.com", "u", "p")

    await upsert_server_group_traffic_template(
        gid,
        enabled=True,
        limited_bucket_name="L",
        limit_bytes=10 * 1024 * 1024 * 1024,
        is_unlimited=False,
        window_days=30,
        credit_periods_total=1,
    )
    await replace_server_group_traffic_limited_servers(gid, [s_lim])

    subscriber_id = await get_or_create_subscriber(f"u_gt_{suffix}")
    now = int(time.time())
    sub_id, _ = await create_subscription(
        subscriber_id=subscriber_id,
        period="month",
        device_limit=1,
        price=1.0,
        expires_at=now + 86400 * 30,
        name="sub",
        group_id=gid,
    )

    r = await apply_template_to_subscription(sub_id, force=False, dry_run=False)
    assert r.get("ok") is True
    assert r.get("applied") is True

    buckets = await list_subscription_traffic_buckets(sub_id)
    names = {b["name"] for b in buckets}
    assert "unlimited" in names
    assert group_limited_bucket_stable_name(gid) in names

    m = await get_subscription_server_bucket_map(sub_id)
    lim_id = next(b["id"] for b in buckets if b["name"] == group_limited_bucket_stable_name(gid))
    def_id = next(b["id"] for b in buckets if b["name"] == "unlimited")
    assert m.get(s_lim) == lim_id
    assert m.get(s_free) == def_id


@pytest.mark.asyncio
async def test_dry_run_does_not_insert_traffic_buckets(db, monkeypatch):
    """Dry-run не должен создавать пакеты в БД (раньше вызывался ensure_default_unlimited_bucket)."""
    monkeypatch.setenv("DARALLA_TRAFFIC_BUCKETS_ENABLED", "1")
    suffix = uuid.uuid4().hex[:8]
    gid = await add_server_group(f"GDry_{suffix}", description="t", is_default=False)
    s_lim = f"lim_d_{suffix}"
    s_free = f"free_d_{suffix}"
    await add_server_config(gid, s_lim, "https://example.com", "u", "p")
    await add_server_config(gid, s_free, "https://example.com", "u", "p")
    await upsert_server_group_traffic_template(
        gid,
        enabled=True,
        limited_bucket_name="L",
        limit_bytes=10 * 1024 * 1024 * 1024,
        is_unlimited=False,
        window_days=30,
        credit_periods_total=1,
    )
    await replace_server_group_traffic_limited_servers(gid, [s_lim])

    subscriber_id = await get_or_create_subscriber(f"u_dry_{suffix}")
    now = int(time.time())
    sub_id, _ = await create_subscription(
        subscriber_id=subscriber_id,
        period="month",
        device_limit=1,
        price=1.0,
        expires_at=now + 86400 * 30,
        group_id=gid,
    )
    assert len(await list_subscription_traffic_buckets(sub_id)) == 0

    r = await apply_template_to_subscription(sub_id, force=False, dry_run=True)
    assert r.get("ok") is True
    assert r.get("would_apply") is True

    assert len(await list_subscription_traffic_buckets(sub_id)) == 0


@pytest.mark.asyncio
async def test_apply_skips_when_custom_bucket(db, monkeypatch):
    monkeypatch.setenv("DARALLA_TRAFFIC_BUCKETS_ENABLED", "1")
    suffix = uuid.uuid4().hex[:8]
    gid = await add_server_group(f"GSkip_{suffix}", description="t", is_default=False)
    await add_server_config(gid, f"n_{suffix}", "https://example.com", "u", "p")

    await upsert_server_group_traffic_template(
        gid,
        enabled=True,
        limited_bucket_name="L",
        limit_bytes=1024**3,
        is_unlimited=False,
        window_days=30,
        credit_periods_total=1,
    )
    await replace_server_group_traffic_limited_servers(gid, [f"n_{suffix}"])

    subscriber_id = await get_or_create_subscriber(f"u_sk_{suffix}")
    now = int(time.time())
    sub_id, _ = await create_subscription(
        subscriber_id=subscriber_id,
        period="month",
        device_limit=1,
        price=1.0,
        expires_at=now + 86400 * 30,
        group_id=gid,
    )
    await create_subscription_traffic_bucket(sub_id, "my_custom_pack", limit_bytes=1024, is_unlimited=False)

    r = await apply_template_to_subscription(sub_id, force=False, dry_run=False)
    assert r.get("skipped") is True
    assert r.get("reason") == "custom_traffic"

    r2 = await apply_template_to_subscription(sub_id, force=True, dry_run=False)
    assert r2.get("applied") is True


@pytest.mark.asyncio
async def test_bulk_dry_run(db, monkeypatch):
    monkeypatch.setenv("DARALLA_TRAFFIC_BUCKETS_ENABLED", "1")
    suffix = uuid.uuid4().hex[:8]
    gid = await add_server_group(f"GBulk_{suffix}", description="t", is_default=False)
    await add_server_config(gid, f"only_{suffix}", "https://example.com", "u", "p")

    await upsert_server_group_traffic_template(
        gid,
        enabled=True,
        limited_bucket_name="L",
        limit_bytes=1024**2,
        is_unlimited=False,
        window_days=30,
        credit_periods_total=1,
    )
    await replace_server_group_traffic_limited_servers(gid, [f"only_{suffix}"])

    subscriber_id = await get_or_create_subscriber(f"u_bk_{suffix}")
    now = int(time.time())
    await create_subscription(
        subscriber_id=subscriber_id,
        period="month",
        device_limit=1,
        price=1.0,
        expires_at=now + 86400 * 30,
        group_id=gid,
    )

    out = await apply_group_traffic_template_bulk(gid, force=False, dry_run=True)
    assert out["ok"] is True
    assert out["total"] >= 1
    assert out["applied"] >= 1
