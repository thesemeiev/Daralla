"""Integration tests: server delete/rename lifecycle and outbox resilience."""
import time
import uuid
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest

from daralla_backend.db import (
    DB_PATH,
    add_server_config,
    add_server_group,
    add_subscription_server,
    create_subscription,
    create_subscription_traffic_bucket,
    delete_server_config,
    enqueue_sync_job,
    get_or_create_subscriber,
    replace_server_group_traffic_limited_servers,
    server_name_exists_in_config,
    set_subscription_server_bucket,
    update_server_config,
    upsert_server_group_traffic_template,
    upsert_subscription_traffic_snapshot,
)
from daralla_backend.services.sync_outbox_service import process_outbox_once


async def _count_rows(table: str, server_name: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            f"SELECT COUNT(*) FROM {table} WHERE server_name = ?",
            (server_name,),
        ) as cur:
            row = await cur.fetchone()
            return int(row[0] if row else 0)


@pytest.mark.asyncio
async def test_delete_server_purges_outbox_and_links(db):
    suffix = uuid.uuid4().hex[:8]
    gid = await add_server_group(f"GLife_{suffix}", description="t", is_default=False)
    server_name = f"srv_del_{suffix}"
    sid = await add_server_config(gid, server_name, "https://example.com", "u", "p")

    subscriber_id = await get_or_create_subscriber(f"u_life_{suffix}")
    now = int(time.time())
    sub_id, _token = await create_subscription(
        subscriber_id=subscriber_id,
        period="month",
        device_limit=1,
        price=1.0,
        expires_at=now + 86400 * 30,
        group_id=gid,
    )
    client_email = f"c_{suffix}@test.local"
    await add_subscription_server(sub_id, server_name, client_email, None)
    bucket_id = await create_subscription_traffic_bucket(
        sub_id,
        "lim",
        limit_bytes=1024**3,
        is_unlimited=False,
    )
    await set_subscription_server_bucket(sub_id, server_name, bucket_id)
    await upsert_subscription_traffic_snapshot(sub_id, server_name, client_email, up=0, down=0)
    await upsert_server_group_traffic_template(
        gid,
        enabled=True,
        limited_bucket_name="L",
        limit_bytes=1024**3,
        is_unlimited=False,
        window_days=30,
        credit_periods_total=1,
    )
    await replace_server_group_traffic_limited_servers(gid, [server_name])
    await enqueue_sync_job(
        subscription_id=sub_id,
        server_name=server_name,
        client_email=client_email,
        desired_revision=1,
    )

    assert await _count_rows("subscription_servers", server_name) == 1
    assert await _count_rows("subscription_server_traffic_bucket_map", server_name) == 1
    assert await _count_rows("subscription_server_traffic_snapshots", server_name) == 1
    assert await _count_rows("server_group_traffic_limited_servers", server_name) == 1
    assert await _count_rows("sync_outbox", server_name) == 1

    deleted, purge_stats = await delete_server_config(sid)
    assert deleted is True
    assert purge_stats.get("subscription_servers", 0) >= 1
    assert purge_stats.get("sync_outbox", 0) >= 1

    assert await _count_rows("subscription_servers", server_name) == 0
    assert await _count_rows("subscription_server_traffic_bucket_map", server_name) == 0
    assert await _count_rows("subscription_server_traffic_snapshots", server_name) == 0
    assert await _count_rows("server_group_traffic_limited_servers", server_name) == 0
    assert await _count_rows("sync_outbox", server_name) == 0
    assert await server_name_exists_in_config(server_name) is False


@pytest.mark.asyncio
async def test_rename_server_propagates_outbox_and_map(db):
    suffix = uuid.uuid4().hex[:8]
    gid = await add_server_group(f"GRen_{suffix}", description="t", is_default=False)
    old_name = f"srv_old_{suffix}"
    new_name = f"srv_new_{suffix}"
    sid = await add_server_config(gid, old_name, "https://example.com", "u", "p")

    subscriber_id = await get_or_create_subscriber(f"u_ren_{suffix}")
    now = int(time.time())
    sub_id, _token = await create_subscription(
        subscriber_id=subscriber_id,
        period="month",
        device_limit=1,
        price=1.0,
        expires_at=now + 86400 * 30,
        group_id=gid,
    )
    client_email = f"c_ren_{suffix}@test.local"
    await add_subscription_server(sub_id, old_name, client_email, None)
    bucket_id = await create_subscription_traffic_bucket(
        sub_id,
        "lim",
        limit_bytes=1024**3,
        is_unlimited=False,
    )
    await set_subscription_server_bucket(sub_id, old_name, bucket_id)
    await replace_server_group_traffic_limited_servers(gid, [old_name])
    await enqueue_sync_job(
        subscription_id=sub_id,
        server_name=old_name,
        client_email=client_email,
        desired_revision=1,
    )

    ok = await update_server_config(sid, name=new_name)
    assert ok is True
    assert await server_name_exists_in_config(old_name) is False
    assert await server_name_exists_in_config(new_name) is True

    assert await _count_rows("subscription_servers", old_name) == 0
    assert await _count_rows("subscription_server_traffic_bucket_map", old_name) == 0
    assert await _count_rows("sync_outbox", old_name) == 0
    assert await _count_rows("server_group_traffic_limited_servers", old_name) == 0

    assert await _count_rows("subscription_servers", new_name) == 1
    assert await _count_rows("subscription_server_traffic_bucket_map", new_name) == 1
    assert await _count_rows("sync_outbox", new_name) == 1
    assert await _count_rows("server_group_traffic_limited_servers", new_name) == 1


async def _job_status(server_name: str) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT status FROM sync_outbox WHERE server_name = ? ORDER BY id DESC LIMIT 1",
            (server_name,),
        ) as cur:
            row = await cur.fetchone()
            return str(row["status"]) if row else None


@pytest.mark.asyncio
async def test_outbox_skips_missing_server(db):
    suffix = uuid.uuid4().hex[:8]
    gid = await add_server_group(f"GOut_{suffix}", description="t", is_default=False)
    subscriber_id = await get_or_create_subscriber(f"u_out_{suffix}")
    now = int(time.time())
    sub_id, _token = await create_subscription(
        subscriber_id=subscriber_id,
        period="month",
        device_limit=1,
        price=1.0,
        expires_at=now + 86400 * 30,
        group_id=gid,
    )
    ghost_server = f"ghost_{suffix}"
    client_email = f"c_out_{suffix}@test.local"
    assert await server_name_exists_in_config(ghost_server) is False

    inserted = await enqueue_sync_job(
        subscription_id=sub_id,
        server_name=ghost_server,
        client_email=client_email,
        desired_revision=1,
        next_run_at=now - 60,
    )
    assert inserted is True

    subscription_manager = MagicMock()
    subscription_manager.ensure_client_on_server = AsyncMock(return_value=(True, False))
    result = await process_outbox_once(
        subscription_manager=subscription_manager,
        batch_size=1,
        max_attempts=3,
    )

    assert await _job_status(ghost_server) == "done"
    subscription_manager.ensure_client_on_server.assert_not_called()
