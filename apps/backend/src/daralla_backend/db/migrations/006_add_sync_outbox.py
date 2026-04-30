"""
Добавляет таблицу outbox для синхронизации БД -> 3x-ui.
"""
import aiosqlite

DESCRIPTION = "Таблица sync_outbox для фоновой доставки sync-задач"


async def up(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER NOT NULL,
            server_name TEXT NOT NULL,
            client_email TEXT NOT NULL,
            op TEXT NOT NULL DEFAULT 'ensure_client',
            payload_json TEXT NOT NULL DEFAULT '{}',
            desired_revision INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            next_run_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
            last_error TEXT,
            created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
            updated_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
            done_at INTEGER,
            FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
        )
        """
    )
    await db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_sync_outbox_unique_job
        ON sync_outbox(subscription_id, server_name, client_email, op, desired_revision)
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sync_outbox_status_run
        ON sync_outbox(status, next_run_at, id)
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sync_outbox_subscription
        ON sync_outbox(subscription_id, id)
        """
    )
    await db.commit()
