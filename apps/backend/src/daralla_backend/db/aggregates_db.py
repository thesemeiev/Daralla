"""Helpers for analytics aggregate tables and DB growth observability."""

from __future__ import annotations

import datetime
import logging

import aiosqlite

from . import DB_PATH

logger = logging.getLogger(__name__)


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


async def get_table_row_counts() -> dict[str, int]:
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
