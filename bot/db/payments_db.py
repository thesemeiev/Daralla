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
    except Exception as e:
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
                        res['meta'] = json.loads(res['meta'])
                    return res
                return None
    except Exception as e:
        logger.error(f"GET_PAYMENT_BY_ID error: {e}")
        return None

async def update_payment_status(payment_id: str, status: str) -> bool:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('UPDATE payments SET status = ? WHERE payment_id = ?', (status, payment_id))
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"UPDATE_PAYMENT_STATUS error: {e}")
        return False

async def update_payment_activation(payment_id: str, activated: bool) -> bool:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('UPDATE payments SET activated = ? WHERE payment_id = ?', (1 if activated else 0, payment_id))
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"UPDATE_PAYMENT_ACTIVATION error: {e}")
        return False

async def get_all_pending_payments() -> list:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM payments WHERE status = 'pending'") as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    except Exception as e:
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
                            meta = json.loads(res['meta'])
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
                            res['meta'] = json.loads(res['meta'])
                        return res
                    return None
    except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
        logger.error(f"CLEANUP_EXPIRED_PENDING_PAYMENTS error: {e}")
        return 0
