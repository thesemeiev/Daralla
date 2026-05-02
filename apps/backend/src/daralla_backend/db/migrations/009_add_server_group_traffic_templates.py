"""
Шаблоны трафика на уровне группы серверов (лимитированные ноды + параметры пакета).
"""
import aiosqlite

DESCRIPTION = "Server group traffic templates and limited server names"


async def up(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS server_group_traffic_templates (
            group_id INTEGER PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0,
            limited_bucket_name TEXT NOT NULL DEFAULT 'Лимитированные ноды',
            limit_bytes INTEGER NOT NULL DEFAULT 0,
            is_unlimited INTEGER NOT NULL DEFAULT 0,
            window_days INTEGER NOT NULL DEFAULT 30,
            credit_periods_total INTEGER NOT NULL DEFAULT 1,
            updated_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
            FOREIGN KEY (group_id) REFERENCES server_groups(id)
        )
        """
    )
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS server_group_traffic_limited_servers (
            group_id INTEGER NOT NULL,
            server_name TEXT NOT NULL,
            PRIMARY KEY (group_id, server_name),
            FOREIGN KEY (group_id) REFERENCES server_groups(id)
        )
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sg_traffic_limited_group
        ON server_group_traffic_limited_servers(group_id)
        """
    )
    await db.commit()
