"""
Хранилище привязок локальных подписок к пользователям RemnaWave.
"""
import aiosqlite

from . import DB_PATH


async def init_remnawave_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
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
        await db.commit()


async def upsert_binding(
    subscription_id: int,
    user_id: str,
    panel_user_id: str,
    subscription_url: str | None,
    now_ts: int,
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO remnawave_bindings
                (subscription_id, user_id, panel_user_id, subscription_url, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(subscription_id) DO UPDATE SET
                user_id=excluded.user_id,
                panel_user_id=excluded.panel_user_id,
                subscription_url=excluded.subscription_url,
                updated_at=excluded.updated_at
            """,
            (subscription_id, user_id, panel_user_id, subscription_url, now_ts, now_ts),
        )
        await db.commit()


async def get_binding_by_subscription(subscription_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM remnawave_bindings WHERE subscription_id = ?",
            (subscription_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None
