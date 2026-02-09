"""
Модуль работы с конфигурацией (ключ-значение). Единая БД daralla.db.
"""
import aiosqlite
import logging
import datetime
from . import DB_PATH

logger = logging.getLogger(__name__)


async def init_config_db():
    """Инициализирует таблицу config."""
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
