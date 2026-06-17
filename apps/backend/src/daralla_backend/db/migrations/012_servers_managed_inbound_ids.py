"""
servers_config: managed_inbound_ids — JSON-массив id инбаундов, которыми управляет бот.
"""
import aiosqlite

DESCRIPTION = "servers_config: managed_inbound_ids"


async def up(db: aiosqlite.Connection) -> None:
    try:
        await db.execute(
            "ALTER TABLE servers_config ADD COLUMN managed_inbound_ids TEXT"
        )
    except Exception:
        pass

    db.row_factory = aiosqlite.Row
    async with db.execute("PRAGMA table_info(servers_config)") as cur:
        col_names = {r[1] for r in await cur.fetchall()}
    if "managed_inbound_ids" not in col_names:
        raise RuntimeError("servers_config: не удалось добавить managed_inbound_ids")
