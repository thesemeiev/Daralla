"""
Модуль работы с платежами (Единая БД)
"""
import aiosqlite
import logging
import datetime
import json
from . import DB_PATH

logger = logging.getLogger(__name__)


def _date_key_utc(unix_ts: int) -> str:
    return datetime.datetime.utcfromtimestamp(int(unix_ts)).strftime("%Y-%m-%d")


def _extract_amount_and_gateway(meta_raw) -> tuple[float, str]:
    meta = {}
    if isinstance(meta_raw, dict):
        meta = meta_raw
    elif isinstance(meta_raw, str):
        try:
            meta = json.loads(meta_raw)
        except (TypeError, json.JSONDecodeError):
            meta = {}

    amount_raw = meta.get("price", 0)
    try:
        amount = float(amount_raw)
    except (TypeError, ValueError):
        amount = 0.0
    gateway = str(meta.get("gateway", "yookassa") or "yookassa").strip().lower()
    return amount, gateway

async def init_payments_db():
    """Инициализирует таблицу платежей в единой БД"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                payment_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                meta TEXT,
                activated INTEGER DEFAULT 0
            )
        ''')
        await db.commit()

async def add_payment(payment_id: str, user_id: str, status: str, meta: dict = None):
    try:
        now = int(datetime.datetime.now().timestamp())
        meta_json = json.dumps(meta) if meta else None
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('''
                INSERT INTO payments (payment_id, user_id, status, created_at, meta)
                VALUES (?, ?, ?, ?, ?)
            ''', (payment_id, user_id, status, now, meta_json))
            await db.commit()
            return True
    except aiosqlite.Error as e:
        logger.error(f"ADD_PAYMENT error: {e}")
        return False

async def get_payment_by_id(payment_id: str) -> dict:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM payments WHERE payment_id = ?', (payment_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    res = dict(row)
                    if res['meta']:
                        try:
                            res['meta'] = json.loads(res['meta'])
                        except (TypeError, json.JSONDecodeError):
                            res['meta'] = {}
                    return res
                return None
    except aiosqlite.Error as e:
        logger.error(f"GET_PAYMENT_BY_ID error: {e}")
        return None

async def update_payment_status(payment_id: str, status: str) -> bool:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('UPDATE payments SET status = ? WHERE payment_id = ?', (status, payment_id))
            await db.commit()
            return True
    except aiosqlite.Error as e:
        logger.error(f"UPDATE_PAYMENT_STATUS error: {e}")
        return False

async def update_payment_activation(payment_id: str, activated: bool) -> bool:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('UPDATE payments SET activated = ? WHERE payment_id = ?', (1 if activated else 0, payment_id))
            await db.commit()
            return True
    except aiosqlite.Error as e:
        logger.error(f"UPDATE_PAYMENT_ACTIVATION error: {e}")
        return False

async def get_all_pending_payments() -> list:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM payments WHERE status = 'pending'") as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    except aiosqlite.Error as e:
        logger.error(f"GET_ALL_PENDING_PAYMENTS error: {e}")
        return []

async def get_pending_payment(user_id: str, period: str = None) -> dict:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            if period:
                # Ищем платеж с конкретным периодом в meta (JSON)
                async with db.execute(
                    "SELECT * FROM payments WHERE user_id = ? AND status = 'pending' ORDER BY created_at DESC", 
                    (user_id,)
                ) as cursor:
                    rows = await cursor.fetchall()
                    for row in rows:
                        res = dict(row)
                        if res['meta']:
                            try:
                                meta = json.loads(res['meta'])
                            except (TypeError, json.JSONDecodeError):
                                meta = {}
                            if meta.get('type') == period:
                                res['meta'] = meta
                                return res
                return None
            else:
                # Просто последний ожидающий платеж
                async with db.execute(
                    "SELECT * FROM payments WHERE user_id = ? AND status = 'pending' ORDER BY created_at DESC LIMIT 1", 
                    (user_id,)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        res = dict(row)
                        if res['meta']:
                            try:
                                res['meta'] = json.loads(res['meta'])
                            except (TypeError, json.JSONDecodeError):
                                res['meta'] = {}
                        return res
                    return None
    except aiosqlite.Error as e:
        logger.error(f"GET_PENDING_PAYMENT error: {e}")
        return None

async def upsert_agg_payments_daily_before(cutoff_ts: int) -> int:
    """
    Пересчитывает и upsert-ит дневные агрегаты платежей для записей старше cutoff_ts.
    Возвращает количество затронутых дневных срезов.
    """
    daily = {}
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT created_at, meta
                FROM payments
                WHERE status = 'succeeded' AND activated = 1 AND created_at < ?
                """,
                (cutoff_ts,),
            ) as cur:
                rows = await cur.fetchall()

            for row in rows:
                day = _date_key_utc(row["created_at"])
                amount, gateway = _extract_amount_and_gateway(row["meta"])
                if amount <= 0:
                    continue
                bucket = daily.setdefault(
                    day,
                    {
                        "count": 0,
                        "revenue": 0.0,
                        "yookassa": 0.0,
                        "cryptocloud": 0.0,
                    },
                )
                bucket["count"] += 1
                bucket["revenue"] += amount
                if gateway == "cryptocloud":
                    bucket["cryptocloud"] += amount
                else:
                    bucket["yookassa"] += amount

            if not daily:
                return 0

            now = int(datetime.datetime.now().timestamp())
            for day, values in daily.items():
                await db.execute(
                    """
                    INSERT INTO agg_payments_daily
                        (date, succeeded_count, succeeded_revenue, yookassa_revenue, cryptocloud_revenue, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(date) DO UPDATE SET
                        succeeded_count = excluded.succeeded_count,
                        succeeded_revenue = excluded.succeeded_revenue,
                        yookassa_revenue = excluded.yookassa_revenue,
                        cryptocloud_revenue = excluded.cryptocloud_revenue,
                        updated_at = excluded.updated_at
                    """,
                    (
                        day,
                        values["count"],
                        round(values["revenue"], 2),
                        round(values["yookassa"], 2),
                        round(values["cryptocloud"], 2),
                        now,
                    ),
                )
            await db.commit()
        return len(daily)
    except aiosqlite.Error as e:
        logger.warning("PAYMENTS_AGG_UPSERT skipped: %s", e)
        return 0


async def cleanup_old_payments(days: int = 30, *, dry_run: bool = False) -> int:
    try:
        cutoff = int((datetime.datetime.now() - datetime.timedelta(days=days)).timestamp())
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM payments WHERE created_at < ? AND status != 'pending'",
                (cutoff,),
            ) as cur:
                row = await cur.fetchone()
                count = row[0] if row else 0
        if count <= 0:
            return 0

        agg_days = await upsert_agg_payments_daily_before(cutoff)
        if agg_days > 0:
            logger.info("PAYMENTS_AGG_UPSERT: updated %s daily slices before cleanup", agg_days)

        if dry_run:
            logger.info("PAYMENTS_CLEANUP_DRY_RUN: would delete %s rows older than %s days", count, days)
            return count

        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "DELETE FROM payments WHERE created_at < ? AND status != 'pending'",
                (cutoff,),
            )
            deleted = cursor.rowcount
            await db.commit()
            return deleted
    except aiosqlite.Error as e:
        logger.error(f"CLEANUP_OLD_PAYMENTS error: {e}")
        return 0

async def cleanup_expired_pending_payments(minutes_old: int = 60) -> int:
    try:
        cutoff = int((datetime.datetime.now() - datetime.timedelta(minutes=minutes_old)).timestamp())
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("UPDATE payments SET status = 'expired' WHERE status = 'pending' AND created_at < ?", (cutoff,))
            count = cursor.rowcount
            await db.commit()
            return count
    except aiosqlite.Error as e:
        logger.error(f"CLEANUP_EXPIRED_PENDING_PAYMENTS error: {e}")
        return 0

async def get_daily_revenue_between(start_ts: int, end_ts: int) -> list:
    """Выручку по дням за интервал [start_ts, end_ts] (unix), все календарные дни UTC с нулями."""
    result: dict = {}
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT created_at, meta FROM payments
                WHERE status = 'succeeded' AND activated = 1
                  AND created_at >= ? AND created_at <= ?
                """,
                (int(start_ts), int(end_ts)),
            ) as cur:
                rows = await cur.fetchall()
                for row in rows:
                    meta = {}
                    if row["meta"]:
                        try:
                            meta = json.loads(row["meta"])
                        except (TypeError, json.JSONDecodeError):
                            pass
                    price = float(meta.get("price", 0))
                    if price <= 0:
                        continue
                    date_key = _date_key_utc(row["created_at"])
                    if date_key not in result:
                        result[date_key] = {"date": date_key, "revenue": 0.0, "count": 0}
                    result[date_key]["revenue"] += price
                    result[date_key]["count"] += 1
    except (aiosqlite.Error, ValueError, TypeError) as e:
        logger.error(f"GET_DAILY_REVENUE_BETWEEN error: {e}")

    utc = datetime.timezone.utc
    try:
        start_day = datetime.datetime.fromtimestamp(int(start_ts), tz=utc).date()
        end_day = datetime.datetime.fromtimestamp(int(end_ts), tz=utc).date()
    except (OverflowError, OSError, ValueError):
        return []

    if start_day > end_day:
        return []

    out = []
    d = start_day
    while d <= end_day:
        key = d.strftime("%Y-%m-%d")
        bucket = result.get(key)
        if bucket:
            out.append(
                {
                    "date": key,
                    "revenue": round(float(bucket["revenue"]), 2),
                    "count": int(bucket["count"]),
                }
            )
        else:
            out.append({"date": key, "revenue": 0.0, "count": 0})
        d += datetime.timedelta(days=1)
    return out


async def get_daily_revenue(days: int = 30) -> list:
    """Последние N календарных дней UTC (включая сегодня)."""
    utc = datetime.timezone.utc
    now = datetime.datetime.now(utc)
    today = now.date()
    n = max(1, int(days))
    start_d = today - datetime.timedelta(days=n - 1)
    start_ts = int(datetime.datetime.combine(start_d, datetime.time.min, tzinfo=utc).timestamp())
    end_ts = int(
        datetime.datetime.combine(today + datetime.timedelta(days=1), datetime.time.min, tzinfo=utc).timestamp()
    ) - 1
    return await get_daily_revenue_between(start_ts, end_ts)


async def get_revenue_by_gateway_between(start_ts: int, end_ts: int) -> dict:
    """Выручка по шлюзам за интервал [start_ts, end_ts]."""
    agg: dict = {}
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT meta FROM payments
                WHERE status = 'succeeded' AND activated = 1
                  AND created_at >= ? AND created_at <= ?
                """,
                (int(start_ts), int(end_ts)),
            ) as cur:
                rows = await cur.fetchall()
                for row in rows:
                    meta = {}
                    if row["meta"]:
                        try:
                            meta = json.loads(row["meta"])
                        except (TypeError, json.JSONDecodeError):
                            pass
                    gateway = meta.get("gateway", "yookassa")
                    price = float(meta.get("price", 0))
                    agg[gateway] = agg.get(gateway, 0.0) + price
    except (aiosqlite.Error, ValueError, TypeError) as e:
        logger.error(f"GET_REVENUE_BY_GATEWAY_BETWEEN error: {e}")
    return agg


async def get_revenue_by_gateway(days: int = 30) -> dict:
    """Последние N календарных дней UTC (включая сегодня)."""
    utc = datetime.timezone.utc
    now = datetime.datetime.now(utc)
    today = now.date()
    n = max(1, int(days))
    start_d = today - datetime.timedelta(days=n - 1)
    start_ts = int(datetime.datetime.combine(start_d, datetime.time.min, tzinfo=utc).timestamp())
    end_ts = int(
        datetime.datetime.combine(today + datetime.timedelta(days=1), datetime.time.min, tzinfo=utc).timestamp()
    ) - 1
    return await get_revenue_by_gateway_between(start_ts, end_ts)


async def get_payments_by_user(user_id: str, limit: int = 50) -> list:
    """Возвращает все платежи пользователя"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM payments WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit)
            ) as cursor:
                rows = await cursor.fetchall()
                result = []
                for row in rows:
                    res = dict(row)
                    if res['meta']:
                        try:
                            res['meta'] = json.loads(res['meta'])
                        except (TypeError, json.JSONDecodeError):
                            res['meta'] = {}
                    result.append(res)
                return result
    except aiosqlite.Error as e:
        logger.error(f"GET_PAYMENTS_BY_USER error: {e}")
        return []
