"""
Порядок серверов в группе: мини-приложение, подписка и VPN-клиент.
"""
import aiosqlite

DESCRIPTION = "servers_config: client_sort_order"


async def up(db: aiosqlite.Connection) -> None:
    try:
        await db.execute(
            "ALTER TABLE servers_config ADD COLUMN client_sort_order INTEGER NOT NULL DEFAULT 0"
        )
    except Exception:
        pass

    db.row_factory = aiosqlite.Row
    async with db.execute(
        "SELECT id, group_id FROM servers_config ORDER BY group_id, id"
    ) as cur:
        rows = await cur.fetchall()

    order_in_group: dict[int, int] = {}
    for row in rows:
        gid = row["group_id"]
        idx = order_in_group.get(gid, 0)
        order_in_group[gid] = idx + 1
        await db.execute(
            "UPDATE servers_config SET client_sort_order = ? WHERE id = ?",
            (idx, row["id"]),
        )
