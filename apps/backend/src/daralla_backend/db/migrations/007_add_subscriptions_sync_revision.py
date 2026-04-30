"""
Добавляет sync_revision в subscriptions для защиты от устаревших sync-задач.
"""
import aiosqlite

DESCRIPTION = "Колонка subscriptions.sync_revision и индекс"


async def up(db: aiosqlite.Connection) -> None:
    async with db.execute("PRAGMA table_info(subscriptions)") as cur:
        columns = {row[1] for row in await cur.fetchall()}
    if "sync_revision" not in columns:
        await db.execute(
            "ALTER TABLE subscriptions ADD COLUMN sync_revision INTEGER NOT NULL DEFAULT 0"
        )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_subscriptions_sync_revision ON subscriptions(id, sync_revision)"
    )
    await db.commit()
