"""
Модуль работы с промокодами.
Таблицы: promo_codes, promo_code_uses.
"""
import aiosqlite
from . import DB_PATH


async def init_promo_db():
    """Инициализирует таблицы promo_codes, promo_code_uses."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promo_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                type TEXT NOT NULL,
                period TEXT NOT NULL,
                uses_count INTEGER DEFAULT 0,
                max_uses INTEGER DEFAULT 1,
                expires_at INTEGER,
                is_active INTEGER DEFAULT 1,
                created_at INTEGER NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS promo_code_uses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                promo_code_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                subscription_id INTEGER,
                used_at INTEGER NOT NULL,
                FOREIGN KEY (promo_code_id) REFERENCES promo_codes(id)
            )
        """)

        await db.commit()
