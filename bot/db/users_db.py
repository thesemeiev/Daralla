"""
Модуль: список account_id (из accounts).
"""
import aiosqlite
import logging
from . import DB_PATH

logger = logging.getLogger(__name__)


async def init_users_db():
    """Резерв для совместимости (accounts создаются в accounts_db)."""
    pass

async def get_all_account_ids(min_last_seen: int = None) -> list:
    """Возвращает список всех account_id (как строки)."""
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
