"""
Бэкофилл: привести subscription_traffic_quota к календарной модели (UTC месяц).
included_allowance = base_monthly из шаблона группы или limit_bytes bucket;
included_used = 0; purchased не трогаем; period_started_at = начало текущего UTC-месяца.
"""

import time
from datetime import datetime, timezone

import aiosqlite

DESCRIPTION = "Bootstrap traffic quota rows for calendar month (UTC)"


def _month_start_unix(ts: int) -> int:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    start = datetime(dt.year, dt.month, 1, tzinfo=timezone.utc)
    return int(start.timestamp())


async def up(db: aiosqlite.Connection) -> None:
    db.row_factory = aiosqlite.Row
    now_ts = int(time.time())
    month_start = _month_start_unix(now_ts)

    async with db.execute(
        """
        SELECT q.subscription_id, q.limited_bucket_id, q.purchased_remaining_bytes, s.group_id
        FROM subscription_traffic_quota q
        JOIN subscriptions s ON s.id = q.subscription_id
        WHERE s.status != 'deleted'
        """
    ) as cur:
        rows = await cur.fetchall()

    for r in rows:
        sid = int(r["subscription_id"])
        bucket_id = int(r["limited_bucket_id"])
        gid = r["group_id"]
        base = 0

        if gid is not None:
            async with db.execute(
                """
                SELECT enabled, is_unlimited, limit_bytes
                FROM server_group_traffic_templates
                WHERE group_id = ?
                LIMIT 1
                """,
                (int(gid),),
            ) as c2:
                tmpl = await c2.fetchone()
            if tmpl and int(tmpl["enabled"] or 0) and not int(tmpl["is_unlimited"] or 0):
                lb = max(0, int(tmpl["limit_bytes"] or 0))
                if lb > 0:
                    base = lb

        if base <= 0:
            async with db.execute(
                """
                SELECT id, subscription_id, limit_bytes, is_unlimited
                FROM subscription_traffic_buckets
                WHERE id = ?
                """,
                (bucket_id,),
            ) as c3:
                b = await c3.fetchone()
            if not b or int(b["is_unlimited"] or 0):
                continue
            if int(b["subscription_id"]) != sid:
                continue
            base = max(0, int(b["limit_bytes"] or 0))

        if base <= 0:
            continue

        await db.execute(
            """
            UPDATE subscription_traffic_quota SET
                limited_bucket_id = ?,
                included_allowance_bytes = ?,
                included_used_bytes = 0,
                period_started_at = ?,
                updated_at = ?,
                traffic_period_version = traffic_period_version + 1
            WHERE subscription_id = ?
            """,
            (bucket_id, base, month_start, now_ts, sid),
        )

    await db.commit()
