"""Service layer for admin stats dashboard routes."""

from __future__ import annotations

import time

import aiosqlite

from daralla_backend.db import DB_PATH
from daralla_backend.db.payments_db import get_daily_revenue, get_revenue_by_gateway
from daralla_backend.db.subscriptions_db import get_subscription_statistics


async def _get_user_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT COUNT(*) as count FROM users") as cur:
            row = await cur.fetchone()
            total_users = row["count"] if row else 0
        thirty_days_ago = int(time.time()) - (30 * 24 * 60 * 60)
        async with db.execute(
            "SELECT COUNT(*) as count FROM users WHERE first_seen >= ?",
            (thirty_days_ago,),
        ) as cur:
            row = await cur.fetchone()
            new_users_30d = row["count"] if row else 0
        return total_users, new_users_30d


async def admin_stats_payload():
    stats = await get_subscription_statistics()
    total_users, new_users_30d = await _get_user_stats()
    daily_revenue = await get_daily_revenue(30)
    gateway_split = await get_revenue_by_gateway(30)

    active_subs = stats.get("active", stats.get("active_subscriptions", 0))
    users_with_subs = stats.get("users_with_active_subs", 0)
    conversion_rate = round(users_with_subs / total_users * 100, 1) if total_users > 0 else 0

    return {
        "success": True,
        "stats": {
            "users": {"total": total_users, "new_30d": new_users_30d},
            "subscriptions": {
                "total": stats.get("total", stats.get("total_subscriptions", 0)),
                "active": active_subs,
                "expired": stats.get("expired", stats.get("expired_subscriptions", 0)),
                "deleted": stats.get("deleted", stats.get("deleted_subscriptions", 0)),
                "trial": stats.get("trial", 0),
            },
            "mrr": stats.get("mrr", 0),
            "mrr_change_percent": stats.get("mrr_change_percent", 0),
            "conversion_rate": conversion_rate,
            "daily_revenue": daily_revenue,
            "gateway_split": gateway_split,
        },
    }
