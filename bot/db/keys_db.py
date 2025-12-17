import aiosqlite
import asyncio
import json
import logging
import datetime
import os

# Определяем путь к базам данных относительно корневой папки проекта
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, 'data')
# Создаем папку data если её нет
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, 'vpn_keys.db')
USERS_DB_PATH = os.path.join(DATA_DIR, 'users.db')
logger = logging.getLogger(__name__)

async def init_users_db():
    """Инициализирует таблицы для пользователей и конфигурации"""
    async with aiosqlite.connect(USERS_DB_PATH) as db:
        # Таблица пользователей
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                first_seen INTEGER,
                last_seen INTEGER
            )
        ''')
        
        # Таблица конфигурации
        await db.execute('''
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT,
                description TEXT,
                updated_at INTEGER
            )
        ''')
        
        await db.commit()

async def get_all_user_ids(min_last_seen: int = None) -> list:
    """Возвращает список всех user_id из таблицы users.
    Если передан min_last_seen (unix ts), вернёт только тех, кто был активен после этой даты.
    """
    try:
        async with aiosqlite.connect(USERS_DB_PATH) as db:
            if min_last_seen is not None:
                async with db.execute('SELECT user_id FROM users WHERE last_seen >= ? ORDER BY last_seen DESC', (min_last_seen,)) as cur:
                    rows = await cur.fetchall()
            else:
                async with db.execute('SELECT user_id FROM users ORDER BY last_seen DESC') as cur:
                    rows = await cur.fetchall()
            return [row[0] for row in rows]
    except Exception as e:
        logger.error(f"GET_ALL_USER_IDS error: {e}")
        return []
async def register_simple_user(user_id: str):
    """Регистрирует пользователя в таблице users (upsert)."""
    try:
        now = int(datetime.datetime.now().timestamp())
        async with aiosqlite.connect(USERS_DB_PATH) as db:
            await db.execute('''
                INSERT INTO users (user_id, first_seen, last_seen)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET last_seen = excluded.last_seen
            ''', (user_id, now, now))
            await db.commit()
    except Exception as e:
        logger.error(f"REGISTER_SIMPLE_USER: error user_id={user_id}: {e}")

async def is_known_user(user_id: str) -> bool:
    """Проверяет наличие user_id в таблице users."""
    try:
        async with aiosqlite.connect(USERS_DB_PATH) as db:
            async with db.execute('SELECT 1 FROM users WHERE user_id = ? LIMIT 1', (user_id,)) as cursor:
                return (await cursor.fetchone()) is not None
    except Exception as e:
        logger.error(f"IS_KNOWN_USER error for user_id={user_id}: {e}")
        return False

async def init_payments_db():
    logger.info(f"INIT_PAYMENTS_DB: Начинаем инициализацию базы данных по пути {DB_PATH}")
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            logger.info("INIT_PAYMENTS_DB: Подключение к базе данных успешно")
            await db.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    user_id TEXT,
                    payment_id TEXT PRIMARY KEY,
                    status TEXT,
                    created_at INTEGER,
                    meta TEXT,
                    activated INTEGER DEFAULT 0
                )
            ''')
            logger.info("INIT_PAYMENTS_DB: Таблица payments создана/проверена")
            await db.commit()
            logger.info("INIT_PAYMENTS_DB: Изменения зафиксированы")
    except Exception as e:
        logger.error(f"INIT_PAYMENTS_DB: Ошибка при инициализации: {e}")
        raise

async def add_payment(user_id: str, payment_id: str, status: str, created_at: int, meta: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT OR REPLACE INTO payments (user_id, payment_id, status, created_at, meta, activated)
            VALUES (?, ?, ?, ?, ?, COALESCE((SELECT activated FROM payments WHERE payment_id = ?), 0))
        ''', (user_id, payment_id, status, created_at, json.dumps(meta), payment_id))
        await db.commit()
    logger.info(f"Платёж добавлен: user_id={user_id}, payment_id={payment_id}, status={status}")

async def get_payment(user_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('''
            SELECT user_id, payment_id, status, created_at, meta, activated
            FROM payments
            WHERE user_id = ?
            ORDER BY created_at DESC LIMIT 1
        ''', (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    'user_id': row[0],
                    'payment_id': row[1],
                    'status': row[2],
                    'created_at': row[3],
                    'meta': json.loads(row[4]) if row[4] else {},
                    'activated': bool(row[5])
                }
            return None

async def get_payment_by_id(payment_id: str) -> dict | None:
    """Получает платеж по payment_id (для webhook'ов)"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('''
            SELECT user_id, payment_id, status, created_at, meta, activated
            FROM payments
            WHERE payment_id = ?
        ''', (payment_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    'user_id': row[0],
                    'payment_id': row[1],
                    'status': row[2],
                    'created_at': row[3],
                    'meta': json.loads(row[4]) if row[4] else {},
                    'activated': bool(row[5])
                }
            return None

async def update_payment_status(payment_id: str, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE payments SET status = ? WHERE payment_id = ?', (status, payment_id))
        await db.commit()
    logger.info(f"Статус платежа обновлён: payment_id={payment_id}, status={status}")

async def mark_payment_as_activated(payment_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE payments SET activated = 1 WHERE payment_id = ?', (payment_id,))
        await db.commit()
    logger.info(f"Платёж помечен как активированный: payment_id={payment_id}")

async def update_payment_activation(payment_id: str, activated: int):
    """Обновляет статус активации платежа"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE payments SET activated = ? WHERE payment_id = ?', (activated, payment_id))
        await db.commit()
    logger.info(f"Обновлен статус активации: payment_id={payment_id}, activated={activated}")

async def get_all_pending_payments() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('''
            SELECT user_id, payment_id, status, created_at, meta, activated
            FROM payments
            WHERE status = ?
        ''', ('pending',)) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    'user_id': row[0],
                    'payment_id': row[1],
                    'status': row[2],
                    'created_at': row[3],
                    'meta': json.loads(row[4]) if row[4] else {},
                    'activated': bool(row[5])
                } for row in rows
            ]

async def get_pending_payment(user_id: str, period: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('''
            SELECT user_id, payment_id, status, created_at, meta, activated
            FROM payments
            WHERE user_id = ? AND status = ? AND json_extract(meta, '$.period') = ?
            ORDER BY created_at DESC LIMIT 1
        ''', (user_id, 'pending', period)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    'user_id': row[0],
                    'payment_id': row[1],
                    'status': row[2],
                    'created_at': row[3],
                    'meta': json.loads(row[4]) if row[4] else {},
                    'activated': bool(row[5])
                }
            return None

# Для теста
if __name__ == '__main__':
    asyncio.run(init_payments_db())

async def cleanup_old_payments(days_old: int = 7):
    """
    Очищает старые записи платежей из базы данных
    :param days_old: Удаляет записи старше указанного количества дней
    """
    import time
    cutoff_time = int(time.time()) - (days_old * 24 * 60 * 60)
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Удаляем старые записи
        async with db.execute('''
            DELETE FROM payments 
            WHERE created_at < ? AND status IN ('succeeded', 'canceled', 'refunded')
        ''', (cutoff_time,)) as cursor:
            deleted_count = cursor.rowcount
        
        await db.commit()
    
    logger.info(f"Очищено {deleted_count} старых записей платежей (старше {days_old} дней)")
    return deleted_count


async def cleanup_expired_pending_payments(minutes_old: int = 20):
    """
    Очищает просроченные pending платежи
    :param minutes_old: Удаляет pending платежи старше указанного количества минут
    """
    import time
    cutoff_time = int(time.time()) - (minutes_old * 60)
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Удаляем просроченные pending платежи
        async with db.execute('''
            DELETE FROM payments 
            WHERE created_at < ? AND status = 'pending'
        ''', (cutoff_time,)) as cursor:
            deleted_count = cursor.rowcount
        
        await db.commit()
    
    logger.info(f"Удалено {deleted_count} просроченных pending платежей (старше {minutes_old} минут)")
    return deleted_count




async def get_config(key: str, default_value: str = None) -> str:
    """Получает значение конфигурации по ключу"""
    try:
        async with aiosqlite.connect(USERS_DB_PATH) as db:
            async with db.execute('SELECT value FROM config WHERE key = ?', (key,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else default_value
    except Exception as e:
        logger.error(f"GET_CONFIG: error for key={key} - {e}")
        return default_value

async def set_config(key: str, value: str, description: str = None) -> bool:
    """Устанавливает значение конфигурации"""
    try:
        now = int(datetime.datetime.now().timestamp())
        async with aiosqlite.connect(USERS_DB_PATH) as db:
            await db.execute('''
                INSERT OR REPLACE INTO config (key, value, description, updated_at)
                VALUES (?, ?, ?, ?)
            ''', (key, value, description, now))
            await db.commit()
            logger.info(f"SET_CONFIG: {key} = {value}")
            return True
    except Exception as e:
        logger.error(f"SET_CONFIG: error for key={key}, value={value} - {e}")
        return False

async def get_all_config() -> dict:
    """Получает все настройки конфигурации"""
    try:
        async with aiosqlite.connect(USERS_DB_PATH) as db:
            async with db.execute('SELECT key, value, description FROM config ORDER BY key') as cursor:
                rows = await cursor.fetchall()
                return {row[0]: {'value': row[1], 'description': row[2]} for row in rows}
    except Exception as e:
        logger.error(f"GET_ALL_CONFIG: error - {e}")
        return {}
