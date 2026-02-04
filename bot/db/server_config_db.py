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


def _get_server_manager():
    """Получает server_manager только из контекста приложения (get_app_context())."""
    try:
        from ..context import get_app_context
        ctx = get_app_context()
        return ctx.server_manager if ctx else None
    except Exception as e:
        logger.debug("Не удалось получить server_manager: %s", e)
        return None


async def get_server_load_data():
    """Данные по серверам для админки (список серверов с нулевой нагрузкой — Remnawave)."""
    server_manager = _get_server_manager()
    if not server_manager or not getattr(server_manager, 'servers', None):
        return []
    return [
        {
            'server_name': server.get("name", "Unknown"),
            'online_clients': 0,
            'total_active': 0,
            'offline_clients': 0,
            'avg_online_24h': 0,
            'max_online_24h': 0,
            'min_online_24h': 0,
            'samples_24h': 0,
            'load_percentage': 0,
        }
        for server in server_manager.servers
    ]


async def get_server_groups(only_active: bool = True):
    """Возвращает все группы серверов."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM server_groups"
        if only_active:
            query += " WHERE is_active = 1"
        async with db.execute(query) as cur:
            return [dict(row) for row in await cur.fetchall()]


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


async def add_server_group(name: str, description: str = None, is_default: bool = False):
    """Добавляет новую группу серверов."""
    async with aiosqlite.connect(DB_PATH) as db:
        if is_default:
            await db.execute("UPDATE server_groups SET is_default = 0")
        async with db.execute(
            "INSERT INTO server_groups (name, description, is_default) VALUES (?, ?, ?)",
            (name, description, 1 if is_default else 0),
        ) as cur:
            group_id = cur.lastrowid
            await db.commit()
            return group_id


async def get_least_loaded_group_id():
    """Возвращает ID первой активной группы, в которой есть активные серверы (для Remnawave без локальных подписок)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT g.id FROM server_groups g
            WHERE g.is_active = 1
              AND EXISTS (SELECT 1 FROM servers_config sc WHERE sc.group_id = g.id AND sc.is_active = 1)
            ORDER BY g.id
            LIMIT 1
        """) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def update_server_group(group_id: int, name: str = None, description: str = None, is_active: int = None, is_default: int = None):
    """Обновляет группу серверов."""
    async with aiosqlite.connect(DB_PATH) as db:
        updates, params = [], []
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        if is_active is not None:
            updates.append("is_active = ?")
            params.append(is_active)
        if is_default is not None:
            if is_default == 1:
                await db.execute("UPDATE server_groups SET is_default = 0")
            updates.append("is_default = ?")
            params.append(is_default)
        if not updates:
            return False
        params.append(group_id)
        await db.execute(f"UPDATE server_groups SET {', '.join(updates)} WHERE id = ?", params)
        await db.commit()
        return True


async def delete_server_group(group_id: int):
    """Удаляет группу, если в ней нет серверов."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM servers_config WHERE group_id = ?", (group_id,)) as cur:
            if (await cur.fetchone())[0] > 0:
                raise ValueError("Нельзя удалить группу, в которой есть серверы")
        await db.execute("DELETE FROM server_groups WHERE id = ?", (group_id,))
        await db.commit()
        return True


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


async def get_group_load_statistics():
    """Статистика по группам (активные серверы; подписки в Remnawave не считаем)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT
                g.id, g.name, g.is_active, g.is_default,
                0 as active_subscriptions,
                (SELECT COUNT(*) FROM servers_config WHERE group_id = g.id AND is_active = 1) as active_servers
            FROM server_groups g
        """) as cur:
            return [dict(row) for row in await cur.fetchall()]
