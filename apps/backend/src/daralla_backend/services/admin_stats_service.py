"""Service layer for admin stats dashboard routes."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import aiosqlite

from daralla_backend.db import DB_PATH
from daralla_backend.db.payments_db import get_daily_revenue_between, get_revenue_by_gateway_between
from daralla_backend.db.subscriptions_db import get_subscription_statistics

MAX_ADMIN_REVENUE_SPAN_DAYS = 366
_ALLOWED_REVENUE_PRESETS = frozenset({"7d", "14d", "30d", "month", "custom"})


def _utc_day_start(d) -> int:
    return int(datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc).timestamp())


def _utc_day_end(d) -> int:
    nxt = datetime.combine(d + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    return int(nxt.timestamp()) - 1


def resolve_admin_revenue_window(revenue_range: dict | None) -> tuple[int, int, dict]:
    """UTC-календарные границы для графика выручки и метаданные для ответа."""
    today = datetime.now(timezone.utc).date()
    preset = "30d"
    raw = revenue_range if isinstance(revenue_range, dict) else {}

    p = raw.get("preset")
    if isinstance(p, str) and p.lower().strip() in _ALLOWED_REVENUE_PRESETS:
        preset = p.lower().strip()

    from_d = today - timedelta(days=29)
    to_d = today

    if preset == "custom":
        try:
            from_d = datetime.strptime(str(raw.get("from", ""))[:10], "%Y-%m-%d").date()
            to_d = datetime.strptime(str(raw.get("to", ""))[:10], "%Y-%m-%d").date()
        except ValueError:
            preset = "30d"
            from_d = today - timedelta(days=29)
            to_d = today

    if preset != "custom":
        if preset == "7d":
            from_d = today - timedelta(days=6)
        elif preset == "14d":
            from_d = today - timedelta(days=13)
        elif preset == "30d":
            from_d = today - timedelta(days=29)
        elif preset == "month":
            from_d = today.replace(day=1)
        to_d = today

    if from_d > to_d:
        from_d, to_d = to_d, from_d

    if to_d > today:
        to_d = today
    if from_d > today:
        from_d = today

    span = (to_d - from_d).days + 1
    if span > MAX_ADMIN_REVENUE_SPAN_DAYS:
        from_d = to_d - timedelta(days=MAX_ADMIN_REVENUE_SPAN_DAYS - 1)

    start_ts = _utc_day_start(from_d)
    end_ts = _utc_day_end(to_d)
    meta = {
        "preset": preset,
        "from": from_d.isoformat(),
        "to": to_d.isoformat(),
    }
    return start_ts, end_ts, meta


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


async def admin_stats_payload(revenue_range: dict | None = None):
    stats = await get_subscription_statistics()
    total_users, new_users_30d = await _get_user_stats()
    start_ts, end_ts, revenue_meta = resolve_admin_revenue_window(revenue_range)
    daily_revenue = await get_daily_revenue_between(start_ts, end_ts)
    gateway_split = await get_revenue_by_gateway_between(start_ts, end_ts)

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
            "revenue_range": revenue_meta,
        },
    }
