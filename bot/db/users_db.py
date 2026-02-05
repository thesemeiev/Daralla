"""
Модуль работы с общими пользователями и конфигурацией (Единая БД)
"""
import aiosqlite
import logging
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
