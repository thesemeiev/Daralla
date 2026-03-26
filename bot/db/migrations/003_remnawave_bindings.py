"""
RemnaWave-oriented таблица привязок runtime.
"""
import aiosqlite

DESCRIPTION = "Добавляет таблицу remnawave_bindings"


async def up(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS remnawave_bindings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            panel_user_id TEXT NOT NULL,
            subscription_url TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
        )
        """
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_remnawave_bindings_user ON remnawave_bindings(user_id)"
    )
