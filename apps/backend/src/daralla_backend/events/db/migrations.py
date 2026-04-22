"""
Миграции модуля событий: создание таблиц в общей БД.
"""
import logging
import aiosqlite

# Используем ту же БД, что и основное приложение
from daralla_backend.db import DB_PATH

logger = logging.getLogger(__name__)


async def init_events_tables():
    """Создаёт таблицы модуля событий в единой БД (daralla.db)."""
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
            CREATE TABLE IF NOT EXISTS event_counted_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                referrer_user_id TEXT NOT NULL,
                payment_id TEXT NOT NULL,
                paid_at TEXT NOT NULL,
                FOREIGN KEY (event_id) REFERENCES events(id)
            )
        """)
        await db.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_event_counted_payments_event_payment
            ON event_counted_payments(event_id, payment_id)
            """
        )
        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_event_counted_payments_event_referrer
            ON event_counted_payments(event_id, referrer_user_id)
            """
        )
        await db.execute("""
            CREATE TABLE IF NOT EXISTS event_rewards_granted (
                event_id INTEGER PRIMARY KEY,
                granted_at TEXT NOT NULL,
                FOREIGN KEY (event_id) REFERENCES events(id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_referral_codes (
                user_id TEXT PRIMARY KEY,
                code TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
        """)
        await db.commit()
    logger.info(
        "Таблицы модуля событий инициализированы: "
        "events, event_counted_payments, event_rewards_granted, user_referral_codes"
    )
