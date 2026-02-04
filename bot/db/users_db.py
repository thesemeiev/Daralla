"""
Модуль работы с общими пользователями и конфигурацией (Единая БД)
"""
import aiosqlite
import logging
import datetime
from . import DB_PATH

logger = logging.getLogger(__name__)

async def init_users_db():
    """Инициализирует таблицу config (источник пользователей — accounts в accounts_db)."""
    async with aiosqlite.connect(DB_PATH) as db:
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
    """Возвращает список всех user_id (Remnawave: account_id как строка)."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            if min_last_seen is not None:
                async with db.execute(
                    "SELECT account_id FROM accounts WHERE last_seen >= ? ORDER BY last_seen DESC",
                    (min_last_seen,),
                ) as cur:
                    rows = await cur.fetchall()
            else:
                async with db.execute("SELECT account_id FROM accounts ORDER BY last_seen DESC") as cur:
                    rows = await cur.fetchall()
            return [str(row[0]) for row in rows]
    except Exception as e:
        logger.error(f"GET_ALL_USER_IDS error: {e}")
        return []

async def register_simple_user(user_id: str):
    """Remnawave: no-op (пользователи создаются через get_or_create_account_for_telegram)."""
    pass

async def is_known_user(user_id: str) -> bool:
    """Проверяет наличие пользователя (Remnawave: account_id в таблице accounts)."""
    try:
        if isinstance(user_id, str) and user_id.isdigit():
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT 1 FROM accounts WHERE account_id = ? LIMIT 1", (int(user_id),)) as cursor:
                    return (await cursor.fetchone()) is not None
        return False
    except Exception as e:
        logger.error(f"IS_KNOWN_USER error: {e}")
        return False

async def get_config(key: str, default_value: str = None) -> str:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute('SELECT value FROM config WHERE key = ?', (key,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else default_value
    except Exception as e:
        logger.error(f"GET_CONFIG error: {e}")
        return default_value

async def set_config(key: str, value: str, description: str = None) -> bool:
    try:
        now = int(datetime.datetime.now().timestamp())
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute('''
                INSERT OR REPLACE INTO config (key, value, description, updated_at)
                VALUES (?, ?, ?, ?)
            ''', (key, value, description, now))
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"SET_CONFIG error: {e}")
        return False

async def get_all_config() -> dict:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute('SELECT key, value, description FROM config ORDER BY key') as cursor:
                rows = await cursor.fetchall()
                return {row[0]: {'value': row[1], 'description': row[2]} for row in rows}
    except Exception as e:
        logger.error(f"GET_ALL_CONFIG error: {e}")
        return {}
