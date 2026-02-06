"""
Переопределения расположения нод Remnawave на карте (админка).
"""
import logging
from . import DB_PATH

import aiosqlite

logger = logging.getLogger(__name__)


async def init_server_config_db():
    """Инициализирует таблицу переопределений координат нод Remnawave."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS node_map_overrides (
                node_uuid TEXT PRIMARY KEY,
                lat REAL,
                lng REAL,
                map_label TEXT
            )
        """)
        await db.commit()


async def get_node_map_overrides() -> dict[str, dict]:
    """Возвращает {node_uuid: {lat, lng, map_label}}."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT node_uuid, lat, lng, map_label FROM node_map_overrides"
        ) as cur:
            rows = await cur.fetchall()
            return {
                str(row["node_uuid"]): {
                    "lat": row["lat"],
                    "lng": row["lng"],
                    "map_label": row["map_label"],
                }
                for row in rows
                if row["node_uuid"]
            }


async def upsert_node_map_override(node_uuid: str, lat: float | None = None, lng: float | None = None, map_label: str | None = None) -> bool:
    """Сохраняет переопределение координат/подписи для ноды Remnawave."""
    node_uuid = (node_uuid or "").strip()
    if not node_uuid:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO node_map_overrides (node_uuid, lat, lng, map_label)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(node_uuid) DO UPDATE SET
                 lat = excluded.lat,
                 lng = excluded.lng,
                 map_label = excluded.map_label""",
            (node_uuid, lat, lng, (map_label or "").strip() or None),
        )
        await db.commit()
        return True
