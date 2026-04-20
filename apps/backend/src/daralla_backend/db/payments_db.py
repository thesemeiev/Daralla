"""
Модуль работы с платежами (Единая БД)
"""
import aiosqlite
import logging
import datetime
import json
from . import DB_PATH

logger = logging.getLogger(__name__)

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

async def cleanup_old_payments(days: int = 30) -> int:
    try:
        cutoff = int((datetime.datetime.now() - datetime.timedelta(days=days)).timestamp())
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("DELETE FROM payments WHERE created_at < ? AND status != 'pending'", (cutoff,))
            count = cursor.rowcount
            await db.commit()
            return count
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

async def get_daily_revenue(days: int = 30) -> list:
    """Возвращает выручку по дням за период из таблицы payments."""
    start_ts = int((datetime.datetime.now() - datetime.timedelta(days=days)).timestamp())
    result = {}
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT created_at, meta FROM payments
                WHERE status = 'succeeded' AND activated = 1 AND created_at >= ?
            """, (start_ts,)) as cur:
                rows = await cur.fetchall()
                for row in rows:
                    meta = {}
                    if row['meta']:
                        try:
                            meta = json.loads(row['meta'])
                        except (TypeError, json.JSONDecodeError):
                            pass
                    price = float(meta.get('price', 0))
                    if price <= 0:
                        continue
                    date_key = datetime.datetime.utcfromtimestamp(row['created_at']).strftime('%Y-%m-%d')
                    if date_key not in result:
                        result[date_key] = {'date': date_key, 'revenue': 0, 'count': 0}
                    result[date_key]['revenue'] += price
                    result[date_key]['count'] += 1
    except (aiosqlite.Error, ValueError, TypeError) as e:
        logger.error(f"GET_DAILY_REVENUE error: {e}")
    return sorted(result.values(), key=lambda x: x['date'])


async def get_revenue_by_gateway(days: int = 30) -> dict:
    """Возвращает выручку по платёжным шлюзам за период."""
    start_ts = int((datetime.datetime.now() - datetime.timedelta(days=days)).timestamp())
    result = {}
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT meta FROM payments
                WHERE status = 'succeeded' AND activated = 1 AND created_at >= ?
            """, (start_ts,)) as cur:
                rows = await cur.fetchall()
                for row in rows:
                    meta = {}
                    if row['meta']:
                        try:
                            meta = json.loads(row['meta'])
                        except (TypeError, json.JSONDecodeError):
                            pass
                    gateway = meta.get('gateway', 'yookassa')
                    price = float(meta.get('price', 0))
                    result[gateway] = result.get(gateway, 0) + price
    except (aiosqlite.Error, ValueError, TypeError) as e:
        logger.error(f"GET_REVENUE_BY_GATEWAY error: {e}")
    return result


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
