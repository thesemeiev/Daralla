"""
Модуль работы с конфигурацией серверов (группы и серверы для админки).
"""
import logging
from . import DB_PATH

import aiosqlite

logger = logging.getLogger(__name__)

SERVER_CONFIG_UPDATE_KEYS = [
    'group_id', 'name', 'display_name', 'host', 'login', 'password', 'vpn_host',
    'lat', 'lng', 'is_active', 'subscription_port', 'subscription_url', 'client_flow',
    'map_label', 'location', 'max_concurrent_clients',
]


async def init_server_config_db():
    """Инициализирует таблицы групп серверов и конфигурации серверов."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS server_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                is_active INTEGER DEFAULT 1,
                is_default INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS servers_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                name TEXT NOT NULL UNIQUE,
                display_name TEXT,
                host TEXT NOT NULL,
                login TEXT NOT NULL,
                password TEXT NOT NULL,
                vpn_host TEXT,
                lat REAL,
                lng REAL,
                is_active INTEGER DEFAULT 1,
                subscription_port INTEGER DEFAULT 2096,
                subscription_url TEXT,
                client_flow TEXT,
                map_label TEXT,
                location TEXT,
                max_concurrent_clients INTEGER DEFAULT 50,
                FOREIGN KEY (group_id) REFERENCES server_groups(id)
            )
        """)
        await db.commit()


async def get_or_create_default_group() -> int:
    """Возвращает ID группы по умолчанию (для маркеров на карте). Создаёт её при первом вызове."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM server_groups LIMIT 1") as cur:
            row = await cur.fetchone()
        if row:
            return row[0]
        await db.execute(
            "INSERT INTO server_groups (name, description, is_active, is_default) VALUES (?, ?, 1, 1)",
            ("Серверы", "Маркеры на карте"),
        )
        await db.commit()
        async with db.execute("SELECT id FROM server_groups ORDER BY id DESC LIMIT 1") as cur:
            row = await cur.fetchone()
        return row[0] if row else 1


async def get_servers_config(group_id: int = None, only_active: bool = True):
    """Возвращает конфигурацию серверов, опционально по группе."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM servers_config"
        params = []
        conditions = []
        if group_id is not None:
            conditions.append("group_id = ?")
            params.append(group_id)
        if only_active:
            conditions.append("is_active = 1")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        async with db.execute(query, params) as cur:
            return [dict(row) for row in await cur.fetchall()]


async def get_server_by_id(server_id: int):
    """Возвращает конфигурацию сервера по id или None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM servers_config WHERE id = ?", (server_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def add_server_config(
    group_id: int, name: str, host: str, login: str, password: str,
    display_name: str = None, vpn_host: str = None, lat: float = None, lng: float = None,
    subscription_port: int = None, subscription_url: str = None, client_flow: str = None,
    map_label: str = None, location: str = None, max_concurrent_clients: int = None,
):
    """Добавляет конфигурацию сервера."""
    port = 2096 if subscription_port is None else subscription_port
    cap = 50 if max_concurrent_clients is None else max_concurrent_clients
    loc = (location or "").strip() or None
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """INSERT INTO servers_config
               (group_id, name, display_name, host, login, password, vpn_host, lat, lng,
                subscription_port, subscription_url, client_flow, map_label, location, max_concurrent_clients)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (group_id, name, display_name, host, login, password, vpn_host, lat, lng,
             port, subscription_url, (client_flow or "").strip() or None, (map_label or "").strip() or None, loc, cap),
        ) as cur:
            server_id = cur.lastrowid
            await db.commit()
            return server_id


async def update_server_config(server_id: int, **kwargs):
    """Обновляет конфигурацию сервера (только разрешённые поля)."""
    allowed = {k: kwargs[k] for k in SERVER_CONFIG_UPDATE_KEYS if k in kwargs}
    if not allowed:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        updates = [f"{k} = ?" for k in allowed]
        params = list(allowed.values()) + [server_id]
        await db.execute(f"UPDATE servers_config SET {', '.join(updates)} WHERE id = ?", params)
        await db.commit()
        return True


async def delete_server_config(server_id: int):
    """Удаляет конфигурацию сервера."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM servers_config WHERE id = ?", (server_id,))
        await db.commit()
        return True
