"""Integration tests for retention lifecycle and growth observability."""

import time
import uuid

import aiosqlite
import pytest

from daralla_backend.db import (
    DB_PATH,
    add_payment,
    add_server_config,
    add_server_group,
    cleanup_deleted_subscriptions,
    cleanup_old_payments,
    create_subscription,
    create_telegram_link,
    delete_user_completely,
    get_or_create_subscriber,
    get_subscription_by_id_only,
    get_table_row_counts,
    link_telegram_create_state,
    register_web_user,
    update_payment_activation,
    update_subscription_status,
)


@pytest.mark.asyncio
async def test_payments_retention_dry_run_keeps_rows(db):
    user_id = f"pay_user_{uuid.uuid4().hex[:8]}"
    await get_or_create_subscriber(user_id)
    payment_id = f"pay_old_{uuid.uuid4().hex[:10]}"
    ok = await add_payment(
        payment_id,
        user_id,
        "succeeded",
        {"price": 123.45, "gateway": "yookassa"},
    )
    assert ok is True
    await update_payment_activation(payment_id, True)

    old_ts = int(time.time()) - (400 * 24 * 3600)
    async with aiosqlite.connect(DB_PATH) as db_conn:
        await db_conn.execute(
            "UPDATE payments SET created_at = ? WHERE payment_id = ?",
            (old_ts, payment_id),
        )
        await db_conn.commit()

    candidates = await cleanup_old_payments(days=365, dry_run=True)
    assert candidates >= 1

    async with aiosqlite.connect(DB_PATH) as db_conn:
        async with db_conn.execute(
            "SELECT COUNT(*) FROM payments WHERE payment_id = ?",
            (payment_id,),
        ) as cur:
            row = await cur.fetchone()
    assert row[0] == 1


@pytest.mark.asyncio
async def test_deleted_subscriptions_retention_hard_delete(db):
    suffix = uuid.uuid4().hex[:8]
    gid = await add_server_group(f"RetentionGroup_{suffix}", description="Test", is_default=True)
    await add_server_config(gid, f"ret_srv_{suffix}", "https://example.com", "u", "p")

    user_id = f"ret_sub_user_{suffix}"
    subscriber_id = await get_or_create_subscriber(user_id)
    sub_id, _ = await create_subscription(
        subscriber_id=subscriber_id,
        period="month",
        device_limit=1,
        price=100.0,
        expires_at=int(time.time()) + 3600,
        group_id=gid,
    )
    await update_subscription_status(sub_id, "deleted")
    old_ts = int(time.time()) - (380 * 24 * 3600)
    async with aiosqlite.connect(DB_PATH) as db_conn:
        await db_conn.execute("UPDATE subscriptions SET deleted_at = ? WHERE id = ?", (old_ts, sub_id))
        await db_conn.execute(
            "INSERT INTO sent_notifications (user_id, subscription_id, notification_type, sent_at) VALUES (?, ?, ?, ?)",
            (user_id, sub_id, "test_cleanup", old_ts),
        )
        await db_conn.commit()

    dry_count = await cleanup_deleted_subscriptions(days=365, dry_run=True)
    assert dry_count >= 1
    assert await get_subscription_by_id_only(sub_id) is not None

    deleted = await cleanup_deleted_subscriptions(days=365, dry_run=False)
    assert deleted >= 1
    assert await get_subscription_by_id_only(sub_id) is None


@pytest.mark.asyncio
async def test_delete_user_completely_removes_related_records(db):
    suffix = uuid.uuid4().hex[:8]
    gid = await add_server_group(f"CascadeGroup_{suffix}", description="Test", is_default=True)
    await add_server_config(gid, f"cas_srv_{suffix}", "https://example.com", "u", "p")

    user_id = await register_web_user(f"user_{suffix}", "hash123")
    subscriber_id = await get_or_create_subscriber(user_id)
    sub_id, _ = await create_subscription(
        subscriber_id=subscriber_id,
        period="month",
        device_limit=1,
        price=100.0,
        expires_at=int(time.time()) + 7200,
        group_id=gid,
    )
    await add_payment(f"pay_{suffix}", user_id, "succeeded", {"price": 50})
    await create_telegram_link(f"tg_{suffix}", user_id)
    await link_telegram_create_state(user_id)

    async with aiosqlite.connect(DB_PATH) as db_conn:
        await db_conn.execute(
            "INSERT INTO sent_notifications (user_id, subscription_id, notification_type, sent_at) VALUES (?, ?, ?, ?)",
            (user_id, sub_id, "test", int(time.time())),
        )
        await db_conn.commit()

    stats = await delete_user_completely(user_id)
    assert stats["user_deleted"] is True
    assert stats["payments_deleted"] >= 1
    assert stats["telegram_links_deleted"] >= 1

    async with aiosqlite.connect(DB_PATH) as db_conn:
        checks = {
            "users": "SELECT COUNT(*) FROM users WHERE user_id = ?",
            "payments": "SELECT COUNT(*) FROM payments WHERE user_id = ?",
            "sent_notifications": "SELECT COUNT(*) FROM sent_notifications WHERE user_id = ?",
            "telegram_links": "SELECT COUNT(*) FROM telegram_links WHERE user_id = ?",
            "link_telegram_states": "SELECT COUNT(*) FROM link_telegram_states WHERE user_id = ?",
        }
        for query in checks.values():
            async with db_conn.execute(query, (user_id,)) as cur:
                row = await cur.fetchone()
                assert row[0] == 0


@pytest.mark.asyncio
async def test_table_row_counts_exposes_core_tables(db):
    counts = await get_table_row_counts()
    assert "payments" in counts
    assert "subscriptions" in counts
    assert "server_load_history" in counts
