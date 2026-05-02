"""
Периодная квота включённого трафика и отдельный остаток купленного (sidecar).
"""

import datetime
import time

import aiosqlite


DESCRIPTION = "subscription_traffic_quota sidecar for included + purchased traffic"


async def up(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS subscription_traffic_quota (
            subscription_id INTEGER PRIMARY KEY,
            limited_bucket_id INTEGER NOT NULL,
            included_allowance_bytes INTEGER NOT NULL DEFAULT 0,
            included_used_bytes INTEGER NOT NULL DEFAULT 0,
            purchased_remaining_bytes INTEGER NOT NULL DEFAULT 0,
            traffic_period_version INTEGER NOT NULL DEFAULT 0,
            period_started_at INTEGER,
            updated_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
            FOREIGN KEY (subscription_id) REFERENCES subscriptions(id),
            FOREIGN KEY (limited_bucket_id) REFERENCES subscription_traffic_buckets(id)
        )
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sub_traffic_quota_bucket
        ON subscription_traffic_quota(limited_bucket_id)
        """
    )
    await db.commit()

    # Бэкофилл: по одному лимитированному bucket на подписку (предпочитаем имя group:*:limited).
    db.row_factory = aiosqlite.Row
    async with db.execute(
        """
        SELECT id, subscription_id, name, limit_bytes, window_days, is_unlimited
        FROM subscription_traffic_buckets
        WHERE is_unlimited = 0
        ORDER BY subscription_id ASC, id ASC
        """
    ) as cur:
        rows = await cur.fetchall()

    by_sub: dict[int, list] = {}
    for r in rows:
        sid = int(r["subscription_id"])
        by_sub.setdefault(sid, []).append(dict(r))

    async with db.execute("SELECT id FROM subscriptions") as cur:
        valid_sub_ids = {int(x[0]) for x in await cur.fetchall()}

    now_i = int(time.time())

    for sid, lst in by_sub.items():
        if sid not in valid_sub_ids:
            continue
        preferred = None
        for b in lst:
            n = str(b.get("name") or "")
            if n.startswith("group:") and ":limited" in n:
                preferred = b
                break
        chosen = preferred or lst[0]
        bid = int(chosen["id"])
        limit_b = max(0, int(chosen.get("limit_bytes") or 0))
        if limit_b <= 0:
            continue
        win = max(1, int(chosen.get("window_days") or 30))
        # Оценка текущего расхода по скользящему окну (как раньше) → перенос в included_used
        day_start = (datetime.datetime.utcnow() - datetime.timedelta(days=win - 1)).strftime("%Y-%m-%d")
        async with db.execute(
            """
            SELECT COALESCE(SUM(bytes_used), 0) FROM subscription_traffic_usage_daily
            WHERE bucket_id = ? AND day_utc >= ?
            """,
            (bid, day_start),
        ) as c2:
            urow = await c2.fetchone()
            window_used = int((urow[0] if urow else 0) or 0)
        allowance = limit_b
        included_used = min(window_used, allowance)
        try:
            await db.execute(
                """
                INSERT INTO subscription_traffic_quota
                (subscription_id, limited_bucket_id, included_allowance_bytes, included_used_bytes,
                 purchased_remaining_bytes, traffic_period_version, period_started_at, updated_at)
                VALUES (?, ?, ?, ?, 0, 0, ?, ?)
                """,
                (sid, bid, allowance, included_used, now_i, now_i),
            )
        except aiosqlite.IntegrityError:
            pass
    await db.commit()
