"""
Модуль работы с группами серверов и конфигурацией.
Таблицы: server_groups, servers_config, server_load_history.
"""
import aiosqlite
import datetime
import logging
from . import DB_PATH

logger = logging.getLogger(__name__)

# Разрешённые поля для обновления конфигурации сервера (update_server_config)
SERVER_CONFIG_UPDATE_KEYS = [
    'group_id', 'name', 'display_name', 'host', 'login', 'password', 'vpn_host',
    'lat', 'lng', 'is_active', 'subscription_port', 'subscription_url', 'client_flow',
    'map_label', 'location', 'max_concurrent_clients',
]


async def init_servers_db():
    """Инициализирует таблицы server_groups, servers_config, server_load_history."""
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


# ==================== НАГРУЗКА СЕРВЕРОВ ====================

async def save_server_load_snapshot(server_name: str, online_clients: int, total_active: int, offline_clients: int):
    """
    Сохраняет снимок текущей нагрузки на сервер в историю
    Вызывается периодически (например, каждые 5-10 минут) для накопления данных
    """
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
            logger.error(f"Ошибка сохранения снимка нагрузки для {server_name}: {e}")


async def get_server_load_averages(period_hours: int = 24):
    """
    Возвращает средние значения нагрузки на серверы за указанный период

    Args:
        period_hours: Период в часах для расчета среднего (по умолчанию 24 часа)

    Returns:
        dict: {server_name: {'avg_online': float, 'avg_total': float, 'max_online': int, 'min_online': int, 'samples': int}}
    """
    now = int(datetime.datetime.now().timestamp())
    period_seconds = period_hours * 3600
    start_timestamp = now - period_seconds

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

            result = {}
            for row in rows:
                result[row['server_name']] = {
                    'avg_online': round(row['avg_online'] or 0, 1),
                    'avg_total': round(row['avg_total'] or 0, 1),
                    'max_online': row['max_online'] or 0,
                    'min_online': row['min_online'] or 0,
                    'samples': row['samples'] or 0
                }

            return result


async def cleanup_old_server_load_history(days: int = 7):
    """
    Удаляет старые записи истории нагрузки (старше указанного количества дней)
    Вызывается периодически для очистки БД
    """
    now = int(datetime.datetime.now().timestamp())
    cutoff_timestamp = now - (days * 24 * 3600)

    async with aiosqlite.connect(DB_PATH) as db:
        try:
            async with db.execute("DELETE FROM server_load_history WHERE recorded_at < ?", (cutoff_timestamp,)) as cur:
                deleted = cur.rowcount
            await db.commit()
            if deleted > 0:
                logger.info(f"Удалено {deleted} старых записей истории нагрузки (старше {days} дней)")
        except Exception as e:
            logger.error(f"Ошибка очистки истории нагрузки: {e}")


async def get_server_load_data():
    """
    Возвращает данные о нагрузке на серверы (количество онлайн клиентов на каждом сервере)
    Использует X-UI API для получения реальных данных о количестве клиентов в онлайне
    Возвращает список словарей с ключами: server_name, online_clients, total_active, offline_clients
    """
    def get_server_manager():
        """Получает server_manager из bot.py"""
        try:
            import sys
            import importlib

            bot_module = None

            if 'bot.bot' in sys.modules:
                bot_module = sys.modules['bot.bot']
                logger.debug("Найден bot.bot в sys.modules")
            elif 'bot' in sys.modules:
                bot_module = sys.modules['bot']
                if hasattr(bot_module, 'bot'):
                    bot_module = bot_module.bot
                    logger.debug("Найден bot через sys.modules['bot']")

            if not bot_module:
                try:
                    import bot.bot as bot_module
                    logger.debug("Импортирован bot.bot через абсолютный импорт")
                except ImportError as e:
                    logger.debug(f"Не удалось импортировать bot.bot: {e}")

            if not bot_module:
                try:
                    bot_module = importlib.import_module('bot.bot')
                    logger.debug("Импортирован bot.bot через importlib")
                except ImportError as e:
                    logger.debug(f"Не удалось импортировать через importlib: {e}")

            if bot_module:
                server_mgr = getattr(bot_module, 'server_manager', None)
                logger.info(f"server_manager получен: {server_mgr is not None}")
                if server_mgr:
                    logger.info(f"Количество серверов: {len(server_mgr.servers) if hasattr(server_mgr, 'servers') else 0}")
                return server_mgr
            else:
                logger.warning("Не удалось найти модуль bot.bot")
                return None
        except Exception as e:
            logger.error(f"Ошибка получения server_manager: {e}", exc_info=True)
            return None

    server_manager = get_server_manager()
    if not server_manager:
        logger.warning("server_manager недоступен, возвращаем пустые данные")
        return []

    if not hasattr(server_manager, 'servers') or not server_manager.servers:
        logger.warning("server_manager.servers пуст или недоступен")
        return []

    server_data = []

    logger.info(f"Обработка {len(server_manager.servers)} серверов")
    for server in server_manager.servers:
        server_name = server.get("name", "Unknown")
        xui = server.get("x3")

        logger.debug(f"Обработка сервера {server_name}, xui доступен: {xui is not None}")

        if not xui:
            logger.warning(f"Сервер {server_name}: XUI объект недоступен")
            server_data.append({
                'server_name': server_name,
                'online_clients': 0,
                'total_active': 0,
                'offline_clients': 0
            })
            continue

        try:
            logger.debug(f"Получение данных о нагрузке с сервера {server_name}")
            total_active, online_count, offline_count = await xui.get_online_clients_count()

            logger.info(f"Сервер {server_name}: активных={total_active}, онлайн={online_count}, офлайн={offline_count}")

            capacity = (server.get("config") or {}).get("max_concurrent_clients") or 50
            if capacity <= 0:
                capacity = 50
            load_percentage = min(100, round((online_count / capacity) * 100, 1))

            averages = await get_server_load_averages(period_hours=24)
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
                'load_percentage': load_percentage
            })
        except Exception as e:
            logger.error(f"Ошибка получения данных о нагрузке с сервера {server_name}: {e}", exc_info=True)
            server_data.append({
                'server_name': server_name,
                'online_clients': 0,
                'total_active': 0,
                'offline_clients': 0
            })

    logger.info(f"Возвращаем данные для {len(server_data)} серверов")
    server_data.sort(key=lambda x: x['online_clients'], reverse=True)

    return server_data


# ==================== ГРУППЫ СЕРВЕРОВ И КОНФИГУРАЦИЯ ====================

async def get_server_groups(only_active: bool = True):
    """Возвращает все группы серверов"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM server_groups"
        if only_active:
            query += " WHERE is_active = 1"
        async with db.execute(query) as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]


async def get_servers_config(group_id: int = None, only_active: bool = True):
    """Возвращает конфигурацию серверов, опционально фильтруя по группе"""
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
            rows = await cur.fetchall()
            return [dict(row) for row in rows]


async def get_server_by_id(server_id: int):
    """Возвращает конфигурацию сервера по id или None"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM servers_config WHERE id = ?", (server_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def add_server_group(name: str, description: str = None, is_default: bool = False):
    """Добавляет новую группу серверов"""
    async with aiosqlite.connect(DB_PATH) as db:
        if is_default:
            await db.execute("UPDATE server_groups SET is_default = 0")

        async with db.execute(
            "INSERT INTO server_groups (name, description, is_default) VALUES (?, ?, ?)",
            (name, description, 1 if is_default else 0)
        ) as cur:
            group_id = cur.lastrowid
            await db.commit()
            return group_id


async def add_server_config(group_id: int, name: str, host: str, login: str, password: str,
                           display_name: str = None, vpn_host: str = None, lat: float = None, lng: float = None,
                           subscription_port: int = None, subscription_url: str = None, client_flow: str = None,
                           map_label: str = None, location: str = None, max_concurrent_clients: int = None):
    """Добавляет конфигурацию сервера"""
    port = 2096 if subscription_port is None else subscription_port
    cap = 50 if max_concurrent_clients is None else max_concurrent_clients
    loc = (location or "").strip() or None
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """INSERT INTO servers_config 
               (group_id, name, display_name, host, login, password, vpn_host, lat, lng, subscription_port, subscription_url, client_flow, map_label, location, max_concurrent_clients)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (group_id, name, display_name, host, login, password, vpn_host, lat, lng, port, subscription_url, (client_flow or "").strip() or None, (map_label or "").strip() or None, loc, cap)
        ) as cur:
            server_id = cur.lastrowid
            await db.commit()
            return server_id


async def get_least_loaded_group_id():
    """Возвращает ID наименее загруженной группы (по количеству активных подписок).
    Учитываются только группы, в которых есть хотя бы один активный сервер."""
    async with aiosqlite.connect(DB_PATH) as db:
        query = """
            SELECT g.id, COUNT(s.id) as sub_count
            FROM server_groups g
            LEFT JOIN subscriptions s ON g.id = s.group_id AND s.status = 'active'
            WHERE g.is_active = 1
              AND EXISTS (SELECT 1 FROM servers_config sc WHERE sc.group_id = g.id AND sc.is_active = 1)
            GROUP BY g.id
            ORDER BY sub_count ASC
            LIMIT 1
        """
        async with db.execute(query) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def update_server_group(group_id: int, name: str = None, description: str = None, is_active: int = None, is_default: int = None):
    """Обновляет информацию о группе серверов"""
    async with aiosqlite.connect(DB_PATH) as db:
        updates = []
        params = []
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

        if updates:
            params.append(group_id)
            query = f"UPDATE server_groups SET {', '.join(updates)} WHERE id = ?"
            await db.execute(query, params)
            await db.commit()
            return True
        return False


async def update_server_config(server_id: int, **kwargs):
    """Обновляет конфигурацию сервера"""
    async with aiosqlite.connect(DB_PATH) as db:
        old_name = None
        if 'name' in kwargs:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT name FROM servers_config WHERE id = ?", (server_id,)) as cur:
                row = await cur.fetchone()
                if row:
                    old_name = row[0]

        updates = []
        params = []
        for key, value in kwargs.items():
            if key in SERVER_CONFIG_UPDATE_KEYS:
                updates.append(f"{key} = ?")
                params.append(value)

        if updates:
            params.append(server_id)
            query = f"UPDATE servers_config SET {', '.join(updates)} WHERE id = ?"
            await db.execute(query, params)

            if 'name' in kwargs and old_name and old_name != kwargs['name']:
                new_name = kwargs['name']
                async with db.execute(
                    "UPDATE subscription_servers SET server_name = ? WHERE server_name = ?",
                    (new_name, old_name)
                ) as cur:
                    updated_count = cur.rowcount
                if updated_count > 0:
                    logger.info(f"Обновлено {updated_count} записей в subscription_servers: '{old_name}' -> '{new_name}'")
                else:
                    logger.debug(f"Нет записей в subscription_servers для обновления: '{old_name}' -> '{new_name}'")

            await db.commit()
            return True
        return False


async def delete_server_config(server_id: int):
    """Удаляет конфигурацию сервера"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM servers_config WHERE id = ?", (server_id,))
        await db.commit()
        return True


async def get_group_load_statistics():
    """Возвращает статистику загрузки по группам"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = """
            SELECT 
                g.id, g.name, g.is_active, g.is_default,
                COUNT(DISTINCT s.id) as active_subscriptions,
                (SELECT COUNT(*) FROM servers_config WHERE group_id = g.id AND is_active = 1) as active_servers
            FROM server_groups g
            LEFT JOIN subscriptions s ON g.id = s.group_id AND s.status = 'active'
            GROUP BY g.id
        """
        async with db.execute(query) as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]


async def check_and_run_initial_migration():
    """
    Проверяет, есть ли серверы в БД.
    Если групп серверов нет, возвращает False.
    Серверы должны добавляться через админ-панель.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM server_groups") as cur:
            row = await cur.fetchone()
            if row and row[0] > 0:
                return True
        return False
