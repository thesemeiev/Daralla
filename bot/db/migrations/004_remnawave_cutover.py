"""Final schema cutover to RemnaWave-only."""

DESCRIPTION = "Drop server_groups/subscription_servers and remove subscriptions.group_id"


async def _column_exists(db, table: str, column: str) -> bool:
    async with db.execute(f"PRAGMA table_info({table})") as cur:
        rows = await cur.fetchall()
    return any(row[1] == column for row in rows)


async def _table_exists(db, table: str) -> bool:
    async with db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table,),
    ) as cur:
        return (await cur.fetchone()) is not None


async def up(db):
    await db.execute("PRAGMA foreign_keys = OFF")
    await db.execute("BEGIN")
    try:
        if await _table_exists(db, "subscription_servers"):
            await db.execute("DROP TABLE IF EXISTS subscription_servers")
        if await _table_exists(db, "server_load_history"):
            await db.execute("DROP TABLE IF EXISTS server_load_history")
        if await _table_exists(db, "servers_config"):
            await db.execute("DROP TABLE IF EXISTS servers_config")
        if await _table_exists(db, "server_groups"):
            await db.execute("DROP TABLE IF EXISTS server_groups")

        if await _column_exists(db, "subscriptions", "group_id"):
            await db.execute(
                """
                CREATE TABLE subscriptions_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subscriber_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    period TEXT NOT NULL,
                    device_limit INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    subscription_token TEXT UNIQUE NOT NULL,
                    price REAL NOT NULL,
                    name TEXT,
                    FOREIGN KEY (subscriber_id) REFERENCES users(id)
                )
                """
            )
            await db.execute(
                """
                INSERT INTO subscriptions_new
                (id, subscriber_id, status, period, device_limit, created_at, expires_at, subscription_token, price, name)
                SELECT id, subscriber_id, status, period, device_limit, created_at, expires_at, subscription_token, price, name
                FROM subscriptions
                """
            )
            await db.execute("DROP TABLE subscriptions")
            await db.execute("ALTER TABLE subscriptions_new RENAME TO subscriptions")

        await db.execute("COMMIT")
    except Exception:
        await db.execute("ROLLBACK")
        raise
    finally:
        await db.execute("PRAGMA foreign_keys = ON")
