"""
Модуль работы с конфигурацией серверов (группы, серверы, история нагрузки).
Единая БД daralla.db.
"""
import datetime
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
    """Инициализирует таблицы групп серверов, конфигурации и истории нагрузки в единой БД."""
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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS server_load_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_name TEXT NOT NULL,
                online_clients INTEGER NOT NULL,
                total_active INTEGER NOT NULL,
                offline_clients INTEGER NOT NULL,
                recorded_at INTEGER NOT NULL,
                UNIQUE(server_name, recorded_at)
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_server_load_server_time
            ON server_load_history(server_name, recorded_at DESC)
        """)
        await db.commit()


async def save_server_load_snapshot(server_name: str, online_clients: int, total_active: int, offline_clients: int):
    """Сохраняет снимок нагрузки на сервер в историю."""
    now = int(datetime.datetime.now().timestamp())
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("""
                INSERT OR REPLACE INTO server_load_history
                (server_name, online_clients, total_active, offline_clients, recorded_at)
                VALUES (?, ?, ?, ?, ?)
            """, (server_name, online_clients, total_active, offline_clients, now))
            await db.commit()
        except Exception as e:
            logger.error("Ошибка сохранения снимка нагрузки для %s: %s", server_name, e)


async def get_server_load_averages(period_hours: int = 24):
    """Средние значения нагрузки по серверам за период (часы)."""
    now = int(datetime.datetime.now().timestamp())
    start_timestamp = now - period_hours * 3600
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT
                server_name,
                AVG(online_clients) as avg_online,
                AVG(total_active) as avg_total,
                MAX(online_clients) as max_online,
                MIN(online_clients) as min_online,
                COUNT(*) as samples
            FROM server_load_history
            WHERE recorded_at >= ?
            GROUP BY server_name
        """, (start_timestamp,)) as cur:
            rows = await cur.fetchall()
            return {
                row['server_name']: {
                    'avg_online': round(row['avg_online'] or 0, 1),
                    'avg_total': round(row['avg_total'] or 0, 1),
                    'max_online': row['max_online'] or 0,
                    'min_online': row['min_online'] or 0,
                    'samples': row['samples'] or 0,
                }
                for row in rows
            }


async def cleanup_old_server_load_history(days: int = 7):
    """Удаляет записи истории нагрузки старше указанного числа дней."""
    now = int(datetime.datetime.now().timestamp())
    cutoff = now - days * 24 * 3600
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            async with db.execute("DELETE FROM server_load_history WHERE recorded_at < ?", (cutoff,)) as cur:
                deleted = cur.rowcount
            await db.commit()
            if deleted > 0:
                logger.info("Удалено %s старых записей истории нагрузки (старше %s дней)", deleted, days)
        except Exception as e:
            logger.error("Ошибка очистки истории нагрузки: %s", e)


def _get_server_manager():
    """Получает server_manager из bot (ленивый импорт)."""
    try:
        import sys
        if 'bot.bot' in sys.modules:
            return getattr(sys.modules['bot.bot'], 'server_manager', None)
        if 'bot' in sys.modules:
            bot = sys.modules['bot']
            return getattr(getattr(bot, 'bot', bot), 'server_manager', None)
        import importlib
        bot_module = importlib.import_module('bot.bot')
        return getattr(bot_module, 'server_manager', None)
    except Exception as e:
        logger.debug("Не удалось получить server_manager: %s", e)
        return None


async def get_server_load_data():
    """
    Данные о нагрузке на серверы (онлайн клиенты) через X-UI API.
    Возвращает список словарей: server_name, online_clients, total_active, offline_clients, ...
    """
    server_manager = _get_server_manager()
    if not server_manager or not getattr(server_manager, 'servers', None):
        return []
    server_data = []
    averages = await get_server_load_averages(period_hours=24)
    for server in server_manager.servers:
        server_name = server.get("name", "Unknown")
        xui = server.get("x3")
        if not xui:
            server_data.append({'server_name': server_name, 'online_clients': 0, 'total_active': 0, 'offline_clients': 0})
            continue
        try:
            total_active, online_count, offline_count = xui.get_online_clients_count()
            capacity = (server.get("config") or {}).get("max_concurrent_clients") or 50
            if capacity <= 0:
                capacity = 50
            load_pct = min(100, round((online_count / capacity) * 100, 1))
            server_avg = averages.get(server_name, {})
            server_data.append({
                'server_name': server_name,
                'online_clients': online_count,
                'total_active': total_active,
                'offline_clients': offline_count,
                'avg_online_24h': server_avg.get('avg_online', 0),
                'max_online_24h': server_avg.get('max_online', 0),
                'min_online_24h': server_avg.get('min_online', 0),
                'samples_24h': server_avg.get('samples', 0),
                'load_percentage': load_pct,
            })
        except Exception as e:
            logger.exception("Ошибка нагрузки с сервера %s: %s", server_name, e)
            server_data.append({'server_name': server_name, 'online_clients': 0, 'total_active': 0, 'offline_clients': 0})
    server_data.sort(key=lambda x: x['online_clients'], reverse=True)
    return server_data


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


async def check_and_run_initial_migration():
    """Проверяет, есть ли группы серверов в БД. Если нет — возвращает False."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM server_groups") as cur:
            row = await cur.fetchone()
            return row is not None and row[0] > 0
