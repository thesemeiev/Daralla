"""
Добавляет deleted_at в subscriptions для корректной retention-очистки.
"""
import aiosqlite

DESCRIPTION = "Колонка subscriptions.deleted_at и индекс"


async def up(db: aiosqlite.Connection) -> None:
    async with db.execute("PRAGMA table_info(subscriptions)") as cur:
        columns = {row[1] for row in await cur.fetchall()}
    if "deleted_at" not in columns:
        await db.execute("ALTER TABLE subscriptions ADD COLUMN deleted_at INTEGER")
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_subscriptions_deleted_at ON subscriptions(status, deleted_at)"
    )
    await db.commit()
