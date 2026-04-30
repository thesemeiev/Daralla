"""Helpers for analytics aggregate tables and DB growth observability."""

from __future__ import annotations

import asyncio
import datetime
import logging

import aiosqlite

from . import DB_PATH

logger = logging.getLogger(__name__)
_AGG_SCHEMA_READY = False
_AGG_SCHEMA_LOCK = asyncio.Lock()


OBSERVABILITY_TABLES = (
    "payments",
    "subscriptions",
    "subscription_servers",
    "users",
    "sent_notifications",
    "notification_metrics",
    "server_load_history",
    "event_counted_payments",
    "agg_payments_daily",
    "agg_subscriptions_daily",
    "agg_server_load_daily",
)


async def ensure_aggregate_tables_schema() -> None:
    """Defensive self-heal for legacy DBs with partially applied migration 004."""
    global _AGG_SCHEMA_READY
    if _AGG_SCHEMA_READY:
        return
    async with _AGG_SCHEMA_LOCK:
        if _AGG_SCHEMA_READY:
            return
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS agg_payments_daily (
                    date TEXT PRIMARY KEY,
                    succeeded_count INTEGER NOT NULL DEFAULT 0,
                    succeeded_revenue REAL NOT NULL DEFAULT 0,
                    yookassa_revenue REAL NOT NULL DEFAULT 0,
                    cryptocloud_revenue REAL NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS agg_subscriptions_daily (
                    date TEXT PRIMARY KEY,
                    created_total INTEGER NOT NULL DEFAULT 0,
                    created_paid INTEGER NOT NULL DEFAULT 0,
                    created_trial INTEGER NOT NULL DEFAULT 0,
                    deleted_total INTEGER NOT NULL DEFAULT 0,
                    active_total INTEGER NOT NULL DEFAULT 0,
                    expired_total INTEGER NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS agg_server_load_daily (
                    date TEXT NOT NULL,
                    server_name TEXT NOT NULL,
                    avg_online REAL NOT NULL DEFAULT 0,
                    max_online INTEGER NOT NULL DEFAULT 0,
                    avg_total REAL NOT NULL DEFAULT 0,
                    max_total INTEGER NOT NULL DEFAULT 0,
                    samples INTEGER NOT NULL DEFAULT 0,
                    updated_at INTEGER NOT NULL,
                    PRIMARY KEY (date, server_name)
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_agg_server_load_daily_server_date ON agg_server_load_daily(server_name, date DESC)"
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_agg_server_load_daily_date ON agg_server_load_daily(date DESC)"
            )
            await db.commit()
        _AGG_SCHEMA_READY = True


async def get_table_row_counts() -> dict[str, int]:
    await ensure_aggregate_tables_schema()
    counts: dict[str, int] = {}
    async with aiosqlite.connect(DB_PATH) as db:
        for table in OBSERVABILITY_TABLES:
            try:
                async with db.execute(f"SELECT COUNT(*) FROM {table}") as cur:
                    row = await cur.fetchone()
                    counts[table] = int(row[0]) if row else 0
            except aiosqlite.Error:
                # Таблица может отсутствовать (например events выключены)
                counts[table] = -1
    return counts


async def cleanup_old_daily_aggregates(days: int = 730, *, dry_run: bool = False) -> int:
    await ensure_aggregate_tables_schema()
    cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    tables = ("agg_payments_daily", "agg_subscriptions_daily", "agg_server_load_daily")
    total = 0
    async with aiosqlite.connect(DB_PATH) as db:
        for table in tables:
            try:
                async with db.execute(f"SELECT COUNT(*) FROM {table} WHERE date < ?", (cutoff_date,)) as cur:
                    row = await cur.fetchone()
                    cnt = int(row[0]) if row else 0
                if cnt <= 0:
                    continue
                total += cnt
                if not dry_run:
                    await db.execute(f"DELETE FROM {table} WHERE date < ?", (cutoff_date,))
            except aiosqlite.Error as e:
                logger.warning("AGG_CLEANUP skipped for %s: %s", table, e)
        if not dry_run:
            await db.commit()
    if dry_run and total > 0:
        logger.info(
            "DAILY_AGG_CLEANUP_DRY_RUN: would delete %s rows older than %s days",
            total,
            days,
        )
    return total
