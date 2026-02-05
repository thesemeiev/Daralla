"""
Схема таблиц модуля событий (создание в общей БД app.db).
"""
import logging
import aiosqlite

from bot.db import DB_PATH

logger = logging.getLogger(__name__)


async def init_events_tables():
    """Создаёт таблицы модуля событий в БД app.db."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                start_at TEXT NOT NULL,
                end_at TEXT NOT NULL,
                rewards_json TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS event_referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER,
                referrer_account_id TEXT NOT NULL,
                referred_account_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(referred_account_id, event_id),
                FOREIGN KEY (event_id) REFERENCES events(id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS event_counted_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                referred_account_id TEXT NOT NULL,
                paid_at TEXT NOT NULL,
                UNIQUE(event_id, referred_account_id),
                FOREIGN KEY (event_id) REFERENCES events(id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS event_rewards_granted (
                event_id INTEGER PRIMARY KEY,
                granted_at TEXT NOT NULL,
                FOREIGN KEY (event_id) REFERENCES events(id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_referral_codes (
                account_id TEXT PRIMARY KEY,
                code TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
        """)
        await db.commit()
    logger.info("Таблицы модуля событий инициализированы")
