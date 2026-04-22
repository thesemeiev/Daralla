"""
Добавляет таблицы дневных агрегатов для долгосрочной аналитики.
"""
import aiosqlite

DESCRIPTION = "Таблицы дневных агрегатов (payments/subscriptions/server_load)"


async def up(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS agg_payments_daily (
            date TEXT PRIMARY KEY,                 -- YYYY-MM-DD (UTC)
            succeeded_count INTEGER NOT NULL DEFAULT 0,
            succeeded_revenue REAL NOT NULL DEFAULT 0,
            yookassa_revenue REAL NOT NULL DEFAULT 0,
            cryptocloud_revenue REAL NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL
        )
        """
    )

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS agg_subscriptions_daily (
            date TEXT PRIMARY KEY,                 -- YYYY-MM-DD (UTC)
            created_total INTEGER NOT NULL DEFAULT 0,
            created_paid INTEGER NOT NULL DEFAULT 0,
            created_trial INTEGER NOT NULL DEFAULT 0,
            deleted_total INTEGER NOT NULL DEFAULT 0,
            active_total INTEGER NOT NULL DEFAULT 0,
            expired_total INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL
        )
        """
    )

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS agg_server_load_daily (
            date TEXT NOT NULL,                    -- YYYY-MM-DD (UTC)
            server_name TEXT NOT NULL,
            avg_online REAL NOT NULL DEFAULT 0,
            max_online INTEGER NOT NULL DEFAULT 0,
            avg_total REAL NOT NULL DEFAULT 0,
            max_total INTEGER NOT NULL DEFAULT 0,
            samples INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (date, server_name)
        )
        """
    )

    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_agg_server_load_daily_server_date ON agg_server_load_daily(server_name, date DESC)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_agg_server_load_daily_date ON agg_server_load_daily(date DESC)"
    )
    await db.commit()
