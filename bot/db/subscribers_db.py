"""
Модуль работы с пользователями и их подписками
"""
import aiosqlite
import datetime
import logging
import secrets
import time
import uuid
import json
from . import DB_PATH

logger = logging.getLogger(__name__)

# Разрешённые поля для обновления конфигурации сервера (update_server_config)
SERVER_CONFIG_UPDATE_KEYS = [
    'group_id', 'name', 'display_name', 'host', 'login', 'password', 'vpn_host',
    'lat', 'lng', 'is_active', 'subscription_port', 'subscription_url', 'client_flow',
    'map_label', 'location', 'max_concurrent_clients',
]

async def init_subscribers_db():
    """Инициализирует таблицы пользователей и подписок в единой БД"""
    async with aiosqlite.connect(DB_PATH) as db:
        # 1. Сначала создаем таблицы без зависимостей
        # Единая таблица пользователей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT UNIQUE NOT NULL,
                first_seen INTEGER NOT NULL,
                last_seen INTEGER NOT NULL
            )
        """)

        # Таблица групп серверов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS server_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                is_active INTEGER DEFAULT 1,
                is_default INTEGER DEFAULT 0
            )
        """)

        # 2. Миграции для таблицы users
        try:
            await db.execute("ALTER TABLE users ADD COLUMN username TEXT")
            logger.info("Добавлена колонка username в таблицу users")
        except Exception as e:
            if "duplicate column name" not in str(e).lower():
                logger.error(f"Ошибка миграции (username): {e}")
        
        try:
            await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username) WHERE username IS NOT NULL")
            logger.info("Создан уникальный индекс для username")
        except Exception as e:
            logger.error(f"Ошибка создания индекса для username: {e}")

        try:
            await db.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
            logger.info("Добавлена колонка password_hash в таблицу users")
        except Exception as e:
            if "duplicate column name" not in str(e).lower():
                logger.error(f"Ошибка миграции (password_hash): {e}")
        
        try:
            await db.execute("ALTER TABLE users ADD COLUMN is_web INTEGER DEFAULT 0")
            logger.info("Добавлена колонка is_web в таблицу users")
        except Exception as e:
            if "duplicate column name" not in str(e).lower():
                logger.error(f"Ошибка миграции (is_web): {e}")

        try:
            await db.execute("ALTER TABLE users ADD COLUMN auth_token TEXT")
            logger.info("Добавлена колонка auth_token в таблицу users")
        except Exception as e:
            if "duplicate column name" not in str(e).lower():
                logger.error(f"Ошибка миграции (auth_token): {e}")

        try:
            await db.execute("ALTER TABLE users ADD COLUMN telegram_id TEXT")
            logger.info("Добавлена колонка telegram_id в таблицу users")
        except Exception as e:
            if "duplicate column name" not in str(e).lower():
                logger.error(f"Ошибка миграции (telegram_id): {e}")

        try:
            await db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id) WHERE telegram_id IS NOT NULL"
            )
            logger.info("Создан уникальный индекс idx_users_telegram_id")
        except Exception as e:
            logger.error(f"Ошибка создания индекса idx_users_telegram_id: {e}")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS link_telegram_states (
                state TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)
        logger.info("Таблица link_telegram_states создана/проверена")

        # Таблица связей Telegram ID ↔ аккаунт (user_id)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS telegram_links (
                telegram_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                linked_at INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_telegram_links_user_id 
            ON telegram_links(user_id)
        """)

        # Таблица известных Telegram ID (для контроля выдачи триала)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS known_telegram_ids (
                telegram_id TEXT PRIMARY KEY,
                first_seen_at INTEGER NOT NULL
            )
        """)

        # 3. Создаем таблицы с зависимостями
        # Таблица конфигурации серверов
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
                FOREIGN KEY (group_id) REFERENCES server_groups(id)
            )
        """)

        # Таблица подписок
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscriber_id INTEGER NOT NULL,
                status TEXT NOT NULL,          -- active, expired, deleted
                period TEXT NOT NULL,          -- month, 3month
                device_limit INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                subscription_token TEXT UNIQUE NOT NULL,
                price REAL NOT NULL,
                name TEXT,
                FOREIGN KEY (subscriber_id) REFERENCES users(id)
            )
        """)

        # Миграция: добавляем group_id в subscriptions, если его нет
        try:
            await db.execute("ALTER TABLE subscriptions ADD COLUMN group_id INTEGER")
            logger.info("Добавлена колонка group_id в таблицу subscriptions")
        except Exception as e:
            if "duplicate column name" not in str(e).lower():
                logger.error(f"Ошибка миграции (group_id): {e}")

        # Миграция: заполняем group_id у подписок с NULL (группа по умолчанию)
        try:
            async with db.execute(
                "SELECT id FROM server_groups WHERE is_active = 1 ORDER BY is_default DESC, id ASC LIMIT 1"
            ) as cur:
                row = await cur.fetchone()
            if row is not None:
                default_gid = row[0]
                async with db.execute("UPDATE subscriptions SET group_id = ? WHERE group_id IS NULL", (default_gid,)) as cur:
                    updated = cur.rowcount
                if updated and updated > 0:
                    await db.commit()
                    logger.info("Миграция: заполнен group_id=%s у %s подписок с NULL", default_gid, updated)
        except Exception as e:
            logger.warning("Миграция group_id для существующих подписок: %s", e)

        # Миграция: порт и URL подписки X-UI в настройках сервера
        try:
            await db.execute("ALTER TABLE servers_config ADD COLUMN subscription_port INTEGER DEFAULT 2096")
            logger.info("Добавлена колонка subscription_port в таблицу servers_config")
        except Exception as e:
            if "duplicate column name" not in str(e).lower():
                logger.error(f"Ошибка миграции (subscription_port): {e}")
        try:
            await db.execute("ALTER TABLE servers_config ADD COLUMN subscription_url TEXT")
            logger.info("Добавлена колонка subscription_url в таблицу servers_config")
        except Exception as e:
            if "duplicate column name" not in str(e).lower():
                logger.error(f"Ошибка миграции (subscription_url): {e}")
        try:
            await db.execute("ALTER TABLE servers_config ADD COLUMN client_flow TEXT")
            logger.info("Добавлена колонка client_flow в таблицу servers_config")
        except Exception as e:
            if "duplicate column name" not in str(e).lower():
                logger.error(f"Ошибка миграции (client_flow): {e}")
        try:
            await db.execute("ALTER TABLE servers_config ADD COLUMN map_label TEXT")
            logger.info("Добавлена колонка map_label в таблицу servers_config")
        except Exception as e:
            if "duplicate column name" not in str(e).lower():
                logger.error(f"Ошибка миграции (map_label): {e}")
        try:
            await db.execute("ALTER TABLE servers_config ADD COLUMN location TEXT")
            logger.info("Добавлена колонка location в таблицу servers_config")
        except Exception as e:
            if "duplicate column name" not in str(e).lower():
                logger.error(f"Ошибка миграции (location): {e}")
        try:
            await db.execute("ALTER TABLE servers_config ADD COLUMN max_concurrent_clients INTEGER DEFAULT 50")
            logger.info("Добавлена колонка max_concurrent_clients в таблицу servers_config")
        except Exception as e:
            if "duplicate column name" not in str(e).lower():
                logger.error(f"Ошибка миграции (max_concurrent_clients): {e}")

        # Таблица связей подписки с серверами
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscription_servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscription_id INTEGER NOT NULL,
                server_name TEXT NOT NULL,
                client_email TEXT NOT NULL,
                client_id TEXT,
                FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
            )
        """)

        # Миграция: удаление дублей (subscription_id, server_name) и уникальный индекс
        try:
            await db.execute("""
                DELETE FROM subscription_servers
                WHERE EXISTS (
                    SELECT 1 FROM subscription_servers s2
                    WHERE s2.subscription_id = subscription_servers.subscription_id
                      AND s2.server_name = subscription_servers.server_name
                      AND s2.id < subscription_servers.id
                )
            """)
            logger.info("Миграция subscription_servers: удалены дубли по (subscription_id, server_name)")
            await db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_subscription_servers_unique "
                "ON subscription_servers(subscription_id, server_name)"
            )
            await db.commit()
            logger.info("Создан уникальный индекс idx_subscription_servers_unique на subscription_servers")
        except Exception as e:
            if "UNIQUE constraint" in str(e) or "unique" in str(e).lower():
                logger.warning(
                    "Не удалось создать уникальный индекс subscription_servers: в таблице остались дубли. "
                    "Удалите дубли по (subscription_id, server_name) и перезапустите бота."
                )
            else:
                raise

        # Таблица промокодов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promo_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                type TEXT NOT NULL,              -- 'purchase' или 'extension'
                period TEXT NOT NULL,            -- 'month' или '3month'
                uses_count INTEGER DEFAULT 0,    -- Сколько раз использован
                max_uses INTEGER DEFAULT 1,      -- Максимум использований (0 = безлимит)
                expires_at INTEGER,              -- Дата истечения (NULL = без срока)
                is_active INTEGER DEFAULT 1,     -- Активен ли промокод
                created_at INTEGER NOT NULL
            )
        """)
        
        # Таблица использований промокодов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promo_code_uses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                promo_code_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                subscription_id INTEGER,
                used_at INTEGER NOT NULL,
                FOREIGN KEY (promo_code_id) REFERENCES promo_codes(id)
            )
        """)
        
        # Таблица истории нагрузки на серверы (для расчета средних значений)
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
        
        # Индекс для быстрого поиска по серверу и времени
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_server_load_server_time 
            ON server_load_history(server_name, recorded_at DESC)
        """)
        
        await db.commit()


TG_USER_ID_HEX_LEN = 12  # tg_ + 12 hex = 15 символов всего


def generate_tg_user_id() -> str:
    """Генерирует уникальный короткий user_id для TG-first пользователя (tg_ + 12 hex)."""
    return f"tg_{uuid.uuid4().hex[:TG_USER_ID_HEX_LEN]}"


async def migrate_legacy_numeric_user_ids():
    """
    Миграция: пользователи с числовым user_id (legacy TG-first) получают новый user_id tg_<uuid>
    и явную связь в telegram_links + users.telegram_id.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id FROM users WHERE user_id GLOB '[0-9]*'"
        ) as cur:
            rows = await cur.fetchall()
        old_uids = [row["user_id"] for row in rows]
    if not old_uids:
        return
    for old_uid in old_uids:
        new_uid = generate_tg_user_id()
        try:
            await create_telegram_link(old_uid, new_uid)
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE users SET telegram_id = ? WHERE user_id = ?",
                    (old_uid, old_uid),
                )
                await db.commit()
            await rename_user_id(old_uid, new_uid)
            logger.info(f"Миграция legacy user_id: {old_uid} -> {new_uid}")
        except Exception as e:
            logger.error(f"Ошибка миграции user_id {old_uid}: {e}", exc_info=True)


async def migrate_long_tg_user_ids():
    """
    Миграция: пользователи с длинным tg_ user_id (tg_ + 32 hex) получают короткий формат (tg_ + 12 hex).
    После деплоя все tg_ id будут длиной 15 символов.
    """
    target_len = 3 + TG_USER_ID_HEX_LEN  # "tg_" + 12 hex = 15
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT user_id FROM users WHERE user_id LIKE 'tg_%' AND length(user_id) > ?",
            (target_len,),
        ) as cur:
            rows = await cur.fetchall()
        long_uids = [row["user_id"] for row in rows]
    if not long_uids:
        return
    for old_uid in long_uids:
        for _ in range(10):
            new_uid = generate_tg_user_id()
            existing = await get_user_by_id(new_uid)
            if not existing:
                break
        else:
            logger.error(f"Миграция tg_ shorten: не удалось сгенерировать уникальный id для {old_uid}")
            continue
        try:
            await rename_user_id(old_uid, new_uid)
            logger.info(f"Миграция tg_ shorten: {old_uid} -> {new_uid}")
        except Exception as e:
            logger.error(f"Ошибка миграции tg_ shorten {old_uid}: {e}", exc_info=True)


async def get_or_create_subscriber(user_id: str) -> int:
    """Возвращает внутренний ID пользователя (создаёт, если нет)"""
    now = int(datetime.datetime.now().timestamp())
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            if row:
                await db.execute("UPDATE users SET last_seen = ? WHERE id = ?", (now, row[0]))
                await db.commit()
                return row[0]

        async with db.execute(
            "INSERT INTO users (user_id, first_seen, last_seen) VALUES (?, ?, ?)",
            (user_id, now, now)
        ) as cur:
            user_internal_id = cur.lastrowid
            await db.commit()
            return user_internal_id

async def create_subscription(subscriber_id: int, period: str, device_limit: int, price: float, expires_at: int, name: str = None, group_id: int = None):
    """Создаёт новую подписку. Если group_id не передан — подставляется группа по умолчанию (активная, приоритет is_default)."""
    token = uuid.uuid4().hex[:24]
    now = int(datetime.datetime.now().timestamp())
    async with aiosqlite.connect(DB_PATH) as db:
        if group_id is None:
            async with db.execute(
                """SELECT id FROM server_groups WHERE is_active = 1 ORDER BY is_default DESC, id ASC LIMIT 1"""
            ) as cur:
                row = await cur.fetchone()
                if row is not None:
                    group_id = row[0]
                    logger.debug(f"create_subscription: подставлена группа по умолчанию group_id={group_id}")
        async with db.execute(
            """INSERT INTO subscriptions 
               (subscriber_id, status, period, device_limit, created_at, expires_at, subscription_token, price, name, group_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (subscriber_id, 'active', period, device_limit, now, expires_at, token, price, name, group_id)
        ) as cur:
            sub_id = cur.lastrowid
            await db.commit()
            return sub_id, token

async def get_all_active_subscriptions():
    """Возвращает все активные подписки (с учетом expires_at и исключая deleted)"""
    import time
    current_time = int(time.time())
    
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT s.*, u.user_id 
               FROM subscriptions s 
               JOIN users u ON s.subscriber_id = u.id 
               WHERE s.status = 'active' 
               AND s.expires_at > ?
               AND s.status != 'deleted'""",
            (current_time,)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

async def get_subscriptions_to_sync():
    """
    Возвращает подписки, которые нужно синхронизировать с серверами.
    
    Включает:
    - Активные подписки (status='active' и expires_at > current_time)
    - Истекшие подписки (status='expired' или expires_at < current_time), но не удаленные
    
    Исключает:
    - Удаленные подписки (status='deleted')
    """
    import time
    current_time = int(time.time())
    
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT s.*, u.user_id 
               FROM subscriptions s 
               JOIN users u ON s.subscriber_id = u.id 
               WHERE s.status != 'deleted'
               AND (s.status = 'active' OR s.status = 'expired')""",
        ) as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

async def get_all_active_subscriptions_by_user(user_id: str):
    """Возвращает активные подписки конкретного пользователя"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT s.* 
               FROM subscriptions s 
               JOIN users u ON s.subscriber_id = u.id 
               WHERE u.user_id = ? AND s.status IN ('active', 'expired')
               ORDER BY s.created_at DESC""", (user_id,)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

async def update_subscription_status(subscription_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE subscriptions SET status = ? WHERE id = ?", (status, subscription_id))
        await db.commit()

async def update_subscription_name(subscription_id: int, name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE subscriptions SET name = ? WHERE id = ?", (name, subscription_id))
        await db.commit()

async def update_subscription_expiry(subscription_id: int, new_expires_at: int):
    """Обновляет expires_at и автоматически обновляет статус на основе expires_at"""
    import time
    current_time = int(time.time())
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Получаем текущий статус
        async with db.execute("SELECT status FROM subscriptions WHERE id = ?", (subscription_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                logger.warning(f"Подписка {subscription_id} не найдена при обновлении expires_at")
                return
            current_status = row[0]
        
        # Обновляем expires_at
        await db.execute("UPDATE subscriptions SET expires_at = ? WHERE id = ?", (new_expires_at, subscription_id))
        
        # Автоматически обновляем статус (только если не deleted)
        if current_status != 'deleted':
            if new_expires_at > current_time:
                # Продлеваем - меняем на active, если был expired
                if current_status == 'expired':
                    await db.execute("UPDATE subscriptions SET status = 'active' WHERE id = ?", (subscription_id,))
                    logger.info(f"Подписка {subscription_id} автоматически активирована (продлена до {new_expires_at})")
            else:
                # Истекла - меняем на expired, если был active
                if current_status == 'active':
                    await db.execute("UPDATE subscriptions SET status = 'expired' WHERE id = ?", (subscription_id,))
                    logger.info(f"Подписка {subscription_id} автоматически истекла (expires_at: {new_expires_at})")
        
        await db.commit()

async def update_subscription_device_limit(subscription_id: int, new_device_limit: int):
    """Обновляет лимит устройств/IP для подписки"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE subscriptions SET device_limit = ? WHERE id = ?", (new_device_limit, subscription_id))
        await db.commit()


async def update_subscription_price(subscription_id: int, price: float):
    """Обновляет цену подписки (используется при конверсии пробной в платную через продление)"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE subscriptions SET price = ? WHERE id = ?", (price, subscription_id))
        await db.commit()


def is_subscription_active(sub: dict) -> bool:
    """Проверяет, активна ли подписка (единая логика для всех мест)
    
    Args:
        sub: Словарь с данными подписки (должен содержать 'status' и 'expires_at')
    
    Returns:
        True если подписка активна, False иначе
    """
    import time
    current_time = int(time.time())
    
    # deleted всегда неактивна
    if sub.get('status') == 'deleted':
        return False
    
    # Проверяем статус и expires_at
    return sub.get('status') == 'active' and sub.get('expires_at', 0) > current_time

async def sync_subscription_statuses():
    """Периодически проверяет и обновляет статусы подписок на основе expires_at
    
    Автоматически меняет:
    - active -> expired (если expires_at < current_time)
    - expired -> active (если expires_at > current_time)
    
    Не трогает deleted статус (он финальный)
    
    Returns:
        dict с результатами: {'expired_count': int, 'activated_count': int}
    """
    import time
    current_time = int(time.time())
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Находим подписки, которые должны быть expired, но имеют status='active'
        async with db.execute("""
            UPDATE subscriptions 
            SET status = 'expired' 
            WHERE status = 'active' 
            AND expires_at < ? 
            AND status != 'deleted'
        """, (current_time,)) as cur:
            expired_count = cur.rowcount
        
        # Находим подписки, которые должны быть active, но имеют status='expired'
        async with db.execute("""
            UPDATE subscriptions 
            SET status = 'active' 
            WHERE status = 'expired' 
            AND expires_at > ? 
            AND status != 'deleted'
        """, (current_time,)) as cur:
            activated_count = cur.rowcount
        
        await db.commit()
        
        if expired_count > 0 or activated_count > 0:
            logger.info(f"Синхронизировано статусов: {expired_count} истекло, {activated_count} активировано")
        
        return {
            'expired_count': expired_count,
            'activated_count': activated_count
        }

async def get_subscription_by_token(token: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM subscriptions WHERE subscription_token = ?", (token,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

async def get_subscription_by_id(sub_id: int, user_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT s.* FROM subscriptions s 
               JOIN users u ON s.subscriber_id = u.id 
               WHERE s.id = ? AND u.user_id = ?""", (sub_id, user_id)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

async def get_subscription_by_id_only(sub_id: int):
    """Получает подписку по ID без проверки user_id (для админ-функций)"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT s.*, u.user_id FROM subscriptions s JOIN users u ON s.subscriber_id = u.id WHERE s.id = ?", (sub_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

async def get_subscription_servers(subscription_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM subscription_servers WHERE subscription_id = ?", (subscription_id,)) as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

async def add_subscription_server(subscription_id: int, server_name: str, client_email: str, client_id: str = None):
    """Добавляет связь подписки с сервером. Идемпотентно: не создаёт дубль по (subscription_id, server_name)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM subscription_servers WHERE subscription_id = ? AND server_name = ? LIMIT 1",
            (subscription_id, server_name),
        ) as cur:
            if await cur.fetchone():
                return
        await db.execute(
            "INSERT INTO subscription_servers (subscription_id, server_name, client_email, client_id) VALUES (?, ?, ?, ?)",
            (subscription_id, server_name, client_email, client_id),
        )
        await db.commit()

async def remove_subscription_server(subscription_id: int, server_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM subscription_servers WHERE subscription_id = ? AND server_name = ?", (subscription_id, server_name))
        await db.commit()
        return True

async def get_user_server_usage(user_id: str):
    """
    Возвращает статистику использования серверов пользователем
    Считает, сколько раз пользователь использовал каждый сервер (на основе subscription_servers)
    
    Returns:
        dict: {server_name: {'count': int, 'percentage': float}} - количество использований и процент каждого сервера
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # Получаем все серверы, которые использовал пользователь
        query = """
            SELECT 
                ss.server_name,
                COUNT(*) as usage_count
            FROM subscription_servers ss
            JOIN subscriptions s ON ss.subscription_id = s.id
            JOIN users u ON s.subscriber_id = u.id
            WHERE u.user_id = ?
            GROUP BY ss.server_name
            ORDER BY usage_count DESC
        """
        
        async with db.execute(query, (user_id,)) as cur:
            rows = await cur.fetchall()
        
        # Преобразуем в словарь
        server_usage = {}
        total_usage = 0
        for row in rows:
            server_name = row['server_name']
            usage_count = row['usage_count']
            server_usage[server_name] = usage_count
            total_usage += usage_count
        
        # Рассчитываем проценты
        result = {}
        for server_name, count in server_usage.items():
            percentage = (count / total_usage * 100) if total_usage > 0 else 0
            result[server_name] = {
                'count': count,
                'percentage': round(percentage, 1)
            }
        
        return result

async def get_subscription_statistics():
    """Возвращает статистику по подпискам и пользователям"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        now = int(datetime.datetime.now().timestamp())
        
        # Общее количество пользователей
        async with db.execute("SELECT COUNT(*) as count FROM users") as cur:
            row = await cur.fetchone()
            total_users = row['count'] if row else 0
        
        # Количество активных подписок
        async with db.execute("SELECT COUNT(*) as count FROM subscriptions WHERE status = 'active'") as cur:
            row = await cur.fetchone()
            active_subscriptions = row['count'] if row else 0
        
        # Количество всех подписок (включая истекшие)
        async with db.execute("SELECT COUNT(*) as count FROM subscriptions") as cur:
            row = await cur.fetchone()
            total_subscriptions = row['count'] if row else 0
        
        # Количество истекших подписок
        async with db.execute("SELECT COUNT(*) as count FROM subscriptions WHERE status = 'expired'") as cur:
            row = await cur.fetchone()
            expired_subscriptions = row['count'] if row else 0
        
        # Количество удаленных подписок
        async with db.execute("SELECT COUNT(*) as count FROM subscriptions WHERE status = 'deleted'") as cur:
            row = await cur.fetchone()
            deleted_subscriptions = row['count'] if row else 0
        
        # Количество пробных подписок (trial)
        async with db.execute("SELECT COUNT(*) as count FROM subscriptions WHERE status = 'trial'") as cur:
            row = await cur.fetchone()
            trial_subscriptions = row['count'] if row else 0
        
        # Количество пользователей с активными подписками
        async with db.execute("""
            SELECT COUNT(DISTINCT u.id) as count 
            FROM users u 
            JOIN subscriptions s ON u.id = s.subscriber_id 
            WHERE s.status = 'active'
        """) as cur:
            row = await cur.fetchone()
            users_with_active_subs = row['count'] if row else 0
        
        # Количество клиентов на серверах (из subscription_servers)
        async with db.execute("SELECT COUNT(*) as count FROM subscription_servers") as cur:
            row = await cur.fetchone()
            total_server_clients = row['count'] if row else 0
        
        # Количество клиентов на серверах для активных подписок
        async with db.execute("""
            SELECT COUNT(*) as count 
            FROM subscription_servers ss
            JOIN subscriptions s ON ss.subscription_id = s.id
            WHERE s.status = 'active'
        """) as cur:
            row = await cur.fetchone()
            active_server_clients = row['count'] if row else 0
        
        # Расчет MRR (Monthly Recurring Revenue)
        # MRR = сумма месячных стоимостей всех активных подписок
        async with db.execute("""
            SELECT period, price, COUNT(*) as count
            FROM subscriptions
            WHERE status = 'active' AND price > 0
            GROUP BY period, price
        """) as cur:
            rows = await cur.fetchall()
        
        mrr = 0.0
        for row in rows:
            period = row['period']
            price = row['price']
            count = row['count']
            
            # Определяем месячную стоимость подписки
            if period == 'month':
                monthly_price = price
            elif period == '3month':
                monthly_price = price / 3.0
            else:
                # Для других периодов считаем как месячные (можно расширить логику)
                monthly_price = price
            
            mrr += monthly_price * count
        
        # Расчет MRR за предыдущий месяц для сравнения
        # Берем подписки, которые были активны месяц назад
        month_ago_timestamp = now - (30 * 24 * 60 * 60)
        async with db.execute("""
            SELECT period, price, COUNT(*) as count
            FROM subscriptions
            WHERE status IN ('active', 'expired')
            AND price > 0
            AND created_at <= ?
            AND (expires_at >= ? OR status = 'active')
            GROUP BY period, price
        """, (month_ago_timestamp, month_ago_timestamp)) as cur:
            prev_rows = await cur.fetchall()
        
        prev_mrr = 0.0
        for row in prev_rows:
            period = row['period']
            price = row['price']
            count = row['count']
            
            if period == 'month':
                monthly_price = price
            elif period == '3month':
                monthly_price = price / 3.0
            else:
                monthly_price = price
            
            prev_mrr += monthly_price * count
        
        mrr_change = mrr - prev_mrr
        mrr_change_percent = (mrr_change / prev_mrr * 100) if prev_mrr > 0 else 0.0
        
        return {
            'total_users': total_users,
            'users_with_active_subs': users_with_active_subs,
            # Короткие ключи (для обратной совместимости)
            'total': total_subscriptions,
            'active': active_subscriptions,
            'expired': expired_subscriptions,
            'deleted': deleted_subscriptions,
            'trial': trial_subscriptions,
            # Длинные ключи (для читаемости кода)
            'total_subscriptions': total_subscriptions,
            'active_subscriptions': active_subscriptions,
            'expired_subscriptions': expired_subscriptions,
            'deleted_subscriptions': deleted_subscriptions,
            'trial_subscriptions': trial_subscriptions,
            'total_server_clients': total_server_clients,
            'active_server_clients': active_server_clients,
            # MRR метрики
            'mrr': round(mrr, 2),
            'mrr_change': round(mrr_change, 2),
            'mrr_change_percent': round(mrr_change_percent, 2)
        }

async def get_user_by_id(user_id: str):
    """Возвращает информацию о пользователе по user_id"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_user_by_username(username: str):
    """Возвращает пользователя по логину (username), без ограничения is_web."""
    if not username or not username.strip():
        return None
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE LOWER(TRIM(username)) = LOWER(TRIM(?))",
            (username.strip(),),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def resolve_user_by_query(query: str):
    """
    Находит пользователя по любому идентификатору: Telegram ID, user_id (tg_/web_) или логин.
    Возвращает dict пользователя или None.
    """
    if not query or not query.strip():
        return None
    q = query.strip()
    # Число → telegram_id, затем legacy user_id
    if q.isdigit():
        user = await get_user_by_telegram_id_v2(q, use_fallback=True)
        if user:
            return user
        user = await get_user_by_id(q)
        return user
    # tg_... / web_... → user_id
    if q.startswith("tg_") or q.startswith("web_"):
        return await get_user_by_id(q)
    # Иначе → логин (username)
    user = await get_user_by_username(q)
    if user:
        return user
    # Попробовать как user_id = web_<query>
    return await get_user_by_id(f"web_{q.lower()}")

async def get_user_growth_data(days: int = 30):
    """
    Возвращает данные роста пользователей по дням за указанный период
    Возвращает список словарей с ключами: date (YYYY-MM-DD), count (количество новых пользователей), cumulative (накопительное количество)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # Вычисляем начальную дату
        now = int(datetime.datetime.now().timestamp())
        start_timestamp = now - (days * 24 * 60 * 60)
        
        # Получаем количество пользователей до начала периода (для правильного накопительного подсчета)
        async with db.execute("SELECT COUNT(*) as count FROM users WHERE first_seen < ?", (start_timestamp,)) as cur:
            row = await cur.fetchone()
            users_before_period = row['count'] if row else 0
        
        # Получаем данные о регистрации пользователей по дням
        query = """
            SELECT 
                DATE(first_seen, 'unixepoch') as date,
                COUNT(*) as count
            FROM users
            WHERE first_seen >= ?
            GROUP BY DATE(first_seen, 'unixepoch')
            ORDER BY date ASC
        """
        
        async with db.execute(query, (start_timestamp,)) as cur:
            rows = await cur.fetchall()
            
            # Преобразуем в список словарей
            daily_data = []
            cumulative = users_before_period
            for row in rows:
                cumulative += row['count']
                daily_data.append({
                    'date': row['date'],
                    'count': row['count'],
                    'cumulative': cumulative
                })
            
            return daily_data

async def get_conversion_data(days: int = 30):
    """
    Возвращает данные конверсии по дням за указанный период
    Конверсия = (количество пользователей, которые зарегистрировались в день X и купили подписку) / (количество зарегистрированных в день X) * 100
    
    Возвращает список словарей с ключами:
    - date (YYYY-MM-DD)
    - new_users (количество новых пользователей)
    - purchased (количество купивших подписку)
    - conversion (конверсия в процентах)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # Вычисляем начальную дату
        now = int(datetime.datetime.now().timestamp())
        start_timestamp = now - (days * 24 * 60 * 60)
        
        # Получаем новых пользователей по дням
        query_new_users = """
            SELECT 
                DATE(first_seen, 'unixepoch') as date,
                COUNT(*) as count,
                GROUP_CONCAT(id) as user_ids
            FROM users
            WHERE first_seen >= ?
            GROUP BY DATE(first_seen, 'unixepoch')
            ORDER BY date ASC
        """
        
        async with db.execute(query_new_users, (start_timestamp,)) as cur:
            rows = await cur.fetchall()
        
        # Для каждого дня считаем, сколько из зарегистрированных купили подписку
        daily_data = []
        for row in rows:
            date = row['date']
            new_users_count = row['count']
            user_ids_str = row['user_ids']
            
            if not user_ids_str:
                continue
            
            # Парсим список ID пользователей
            user_ids = [int(uid.strip()) for uid in user_ids_str.split(',') if uid.strip()]
            
            if not user_ids:
                daily_data.append({
                    'date': date,
                    'new_users': new_users_count,
                    'purchased': 0,
                    'conversion': 0.0
                })
                continue
            
            # Считаем, сколько из этих пользователей купили подписку (любую, не только в этот день)
            # Пользователь считается "купившим", если у него есть хотя бы одна подписка со статусом 'active' или была 'expired' (т.е. не trial)
            # Исключаем пробные подписки: status != 'trial' И price > 0
            placeholders = ','.join(['?'] * len(user_ids))
            query_purchased = f"""
                SELECT COUNT(DISTINCT subscriber_id) as count
                FROM subscriptions
                WHERE subscriber_id IN ({placeholders})
                AND status IN ('active', 'expired')
                AND status != 'trial'
                AND price > 0
            """
            
            async with db.execute(query_purchased, user_ids) as cur:
                purchased_row = await cur.fetchone()
                purchased_count = purchased_row['count'] if purchased_row else 0
            
            # Рассчитываем конверсию
            conversion = (purchased_count / new_users_count * 100) if new_users_count > 0 else 0.0
            
            daily_data.append({
                'date': date,
                'new_users': new_users_count,
                'purchased': purchased_count,
                'conversion': round(conversion, 2)
            })
        
        return daily_data

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
    # Получаем server_manager для доступа к XUI объектам
    def get_server_manager():
        """Получает server_manager из bot.py"""
        try:
            import sys
            import importlib
            
            # Пробуем разные способы получения модуля bot
            bot_module = None
            
            # Способ 1: Через sys.modules (самый надежный)
            if 'bot.bot' in sys.modules:
                bot_module = sys.modules['bot.bot']
                logger.debug("Найден bot.bot в sys.modules")
            elif 'bot' in sys.modules:
                bot_module = sys.modules['bot']
                if hasattr(bot_module, 'bot'):
                    bot_module = bot_module.bot
                    logger.debug("Найден bot через sys.modules['bot']")
            
            # Способ 2: Абсолютный импорт
            if not bot_module:
                try:
                    import bot.bot as bot_module
                    logger.debug("Импортирован bot.bot через абсолютный импорт")
                except ImportError as e:
                    logger.debug(f"Не удалось импортировать bot.bot: {e}")
            
            # Способ 3: Динамический импорт
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
    
    # Проходим по всем серверам
    logger.info(f"Обработка {len(server_manager.servers)} серверов")
    for server in server_manager.servers:
        server_name = server.get("name", "Unknown")
        xui = server.get("x3")
        
        logger.debug(f"Обработка сервера {server_name}, xui доступен: {xui is not None}")
        
        if not xui:
            # Сервер недоступен
            logger.warning(f"Сервер {server_name}: XUI объект недоступен")
            server_data.append({
                'server_name': server_name,
                'online_clients': 0,
                'total_active': 0,
                'offline_clients': 0
            })
            continue
        
        try:
            # Получаем количество онлайн клиентов с сервера
            logger.debug(f"Получение данных о нагрузке с сервера {server_name}")
            total_active, online_count, offline_count = xui.get_online_clients_count()
            
            logger.info(f"Сервер {server_name}: активных={total_active}, онлайн={online_count}, офлайн={offline_count}")
            
            # Порог для графика нагрузки из настроек сервера (по умолчанию 50)
            capacity = (server.get("config") or {}).get("max_concurrent_clients") or 50
            if capacity <= 0:
                capacity = 50
            load_percentage = min(100, round((online_count / capacity) * 100, 1))
            
            # Средние за 24 часа для подсказок
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
    # Сортируем по количеству онлайн клиентов
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
            # Снимаем флаг дефолтной с других групп
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
        # ИСПРАВЛЕНИЕ: Получаем старое название перед обновлением
        # Это нужно для обновления связанных записей в subscription_servers
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
            
            # ИСПРАВЛЕНИЕ: Если изменилось название, обновляем связанные записи в subscription_servers
            # Это предотвращает раздвоение серверов при изменении названия в админке
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
        # Проверяем, есть ли группы
        async with db.execute("SELECT COUNT(*) FROM server_groups") as cur:
            row = await cur.fetchone()
            if row and row[0] > 0:
                # База содержит данные групп
                return True
        # Групп нет - серверы должны быть добавлены через админку
        return False

async def get_all_subscriptions_by_user(user_id: str):
    """Возвращает все подписки пользователя (включая истекшие и отмененные)"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT s.* 
               FROM subscriptions s 
               JOIN users u ON s.subscriber_id = u.id 
               WHERE u.user_id = ?
               ORDER BY s.created_at DESC""", (user_id,)
        ) as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

async def get_subscription_types_statistics():
    """
    Возвращает статистику по типам активных подписок (пробные vs купленные)
    
    Returns:
        dict: {
            'trial_active': int,      # Активные пробные подписки (status='trial' или price=0)
            'purchased_active': int,  # Активные купленные подписки (status='active' и price>0 и status!='trial')
            'month_active': int,      # Активные подписки на 1 месяц
            '3month_active': int,     # Активные подписки на 3 месяца
            'total_active': int       # Всего активных подписок
        }
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # Активные пробные подписки (status='trial' ИЛИ (status='active' И price=0))
        async with db.execute("""
            SELECT COUNT(*) as count 
            FROM subscriptions 
            WHERE (status = 'trial' OR (status = 'active' AND price = 0))
        """) as cur:
            row = await cur.fetchone()
            trial_active = row['count'] if row else 0
        
        # Активные купленные подписки (status='active' И price>0 И status!='trial')
        async with db.execute("""
            SELECT COUNT(*) as count 
            FROM subscriptions 
            WHERE status = 'active' 
            AND price > 0
            AND status != 'trial'
        """) as cur:
            row = await cur.fetchone()
            purchased_active = row['count'] if row else 0
        
        # Активные купленные подписки на 1 месяц (исключаем пробные)
        async with db.execute("""
            SELECT COUNT(*) as count 
            FROM subscriptions 
            WHERE status = 'active' 
            AND period = 'month'
            AND price > 0
            AND status != 'trial'
        """) as cur:
            row = await cur.fetchone()
            month_active = row['count'] if row else 0
        
        # Активные купленные подписки на 3 месяца (исключаем пробные)
        async with db.execute("""
            SELECT COUNT(*) as count 
            FROM subscriptions 
            WHERE status = 'active' 
            AND period = '3month'
            AND price > 0
            AND status != 'trial'
        """) as cur:
            row = await cur.fetchone()
            month3_active = row['count'] if row else 0
        
        # Всего активных подписок
        async with db.execute("""
            SELECT COUNT(*) as count 
            FROM subscriptions 
            WHERE status = 'active'
        """) as cur:
            row = await cur.fetchone()
            total_active = row['count'] if row else 0
        
        return {
            'trial_active': trial_active,
            'purchased_active': purchased_active,
            'month_active': month_active,
            '3month_active': month3_active,
            'total_active': total_active
        }

async def get_subscription_dynamics_data(days: int = 30):
    """
    Возвращает динамику подписок по дням за указанный период
    
    Args:
        days: Количество дней для анализа
    
    Returns:
        list: [
            {
                'date': str,              # Дата в формате YYYY-MM-DD
                'trial_active': int,      # Активные пробные в этот день
                'purchased_active': int,  # Активные купленные в этот день
                'trial_created': int,     # Созданные пробные в этот день
                'purchased_created': int  # Созданные купленные в этот день
            },
            ...
        ]
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        now = int(datetime.datetime.now().timestamp())
        start_timestamp = now - (days * 24 * 60 * 60)
        
        # Получаем все подписки, которые могут быть релевантны для периода
        async with db.execute("""
            SELECT 
                created_at,
                expires_at,
                status,
                price
            FROM subscriptions
            WHERE created_at >= ? OR expires_at >= ?
        """, (start_timestamp, start_timestamp)) as cur:
            rows = await cur.fetchall()
        
        # Инициализируем результат для всех дат в периоде
        result = []
        start_date = datetime.datetime.fromtimestamp(start_timestamp).date()
        end_date = datetime.datetime.now().date()
        
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            date_timestamp = int(datetime.datetime.combine(current_date, datetime.time.min).timestamp())
            next_date_timestamp = date_timestamp + 86400
            
            daily_stats = {
                'date': date_str,
                'trial_active': 0,
                'purchased_active': 0,
                'trial_created': 0,
                'purchased_created': 0
            }
            
            # Проверяем каждую подписку для этой даты
            for row in rows:
                created_at = row['created_at']
                expires_at = row['expires_at']
                status = row['status']
                price = row['price']
                
                # Определяем тип подписки
                is_trial = status == 'trial' or price == 0
                
                # Проверяем, была ли подписка создана в этот день
                if date_timestamp <= created_at < next_date_timestamp:
                    if is_trial:
                        daily_stats['trial_created'] += 1
                    else:
                        daily_stats['purchased_created'] += 1
                
                # Проверяем, была ли подписка активна в этот день
                # Используем только даты (не текущий status): создана до конца дня И не истекла к началу дня.
                # Исключаем удалённые — они не учитываются в истории.
                if (status != 'deleted' and
                    created_at < next_date_timestamp and 
                    expires_at >= date_timestamp):
                    if is_trial:
                        daily_stats['trial_active'] += 1
                    else:
                        daily_stats['purchased_active'] += 1
            
            result.append(daily_stats)
            current_date += datetime.timedelta(days=1)
        
        return result

async def delete_user_completely(user_id: str) -> dict:
    """
    Полностью удаляет пользователя и все связанные данные из БД.
    
    Порядок удаления:
    1. Получает все подписки пользователя
    2. Удаляет все связи подписок с серверами (subscription_servers)
    3. Удаляет все подписки (subscriptions)
    4. Удаляет все платежи (payments)
    5. Удаляет все использования промокодов (promo_code_uses)
    6. Удаляет пользователя (users)
    
    Args:
        user_id: Telegram user_id пользователя
        
    Returns:
        dict: {
            'subscriptions_deleted': int,
            'subscription_servers_deleted': int,
            'payments_deleted': int,
            'promo_uses_deleted': int,
            'user_deleted': bool,
            'user_internal_id': int or None
        }
    """
    async with aiosqlite.connect(DB_PATH) as db:
        stats = {
            'subscriptions_deleted': 0,
            'subscription_servers_deleted': 0,
            'payments_deleted': 0,
            'promo_uses_deleted': 0,
            'user_deleted': False,
            'user_internal_id': None
        }
        
        try:
            # Получаем внутренний ID пользователя
            async with db.execute("SELECT id FROM users WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
                if not row:
                    logger.warning(f"Пользователь {user_id} не найден в БД")
                    return stats
                
                user_internal_id = row[0]
                stats['user_internal_id'] = user_internal_id
                
                # Получаем все подписки пользователя
                async with db.execute(
                    "SELECT id FROM subscriptions WHERE subscriber_id = ?",
                    (user_internal_id,)
                ) as cur:
                    subscription_ids = [row[0] for row in await cur.fetchall()]
                
                # 1. Удаляем все связи подписок с серверами
                for sub_id in subscription_ids:
                    async with db.execute(
                        "DELETE FROM subscription_servers WHERE subscription_id = ?",
                        (sub_id,)
                    ) as cur:
                        stats['subscription_servers_deleted'] += cur.rowcount
                
                # 2. Удаляем все подписки
                async with db.execute(
                    "DELETE FROM subscriptions WHERE subscriber_id = ?",
                    (user_internal_id,)
                ) as cur:
                    stats['subscriptions_deleted'] = cur.rowcount
                
                # 3. Удаляем все платежи пользователя
                async with db.execute(
                    "DELETE FROM payments WHERE user_id = ?",
                    (user_id,)
                ) as cur:
                    stats['payments_deleted'] = cur.rowcount
                
                # 4. Удаляем все использования промокодов
                async with db.execute(
                    "DELETE FROM promo_code_uses WHERE user_id = ?",
                    (user_id,)
                ) as cur:
                    stats['promo_uses_deleted'] = cur.rowcount
                
                # 5. Удаляем пользователя
                async with db.execute(
                    "DELETE FROM users WHERE id = ?",
                    (user_internal_id,)
                ) as cur:
                    if cur.rowcount > 0:
                        stats['user_deleted'] = True
                
                await db.commit()
                logger.info(
                    f"Пользователь {user_id} полностью удален: "
                    f"{stats['subscriptions_deleted']} подписок, "
                    f"{stats['subscription_servers_deleted']} связей с серверами, "
                    f"{stats['payments_deleted']} платежей, "
                    f"{stats['promo_uses_deleted']} использований промокодов"
                )
                
        except Exception as e:
            logger.error(f"Ошибка удаления пользователя {user_id}: {e}", exc_info=True)
            await db.rollback()
            raise
        
        return stats

# ==================== АУТЕНТИФИКАЦИЯ (ВЕБ) ====================

async def register_web_user(username: str, password_hash: str):
    """Регистрирует нового веб-пользователя"""
    now = int(datetime.datetime.now().timestamp())
    # Для веб-пользователей user_id будет иметь префикс web_
    user_id = f"web_{username.lower()}"
    
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """INSERT INTO users (user_id, username, password_hash, is_web, first_seen, last_seen) 
                   VALUES (?, ?, ?, 1, ?, ?)""",
                (user_id, username.lower(), password_hash, now, now)
            )
            await db.commit()
            return user_id
        except aiosqlite.IntegrityError:
            raise Exception("Пользователь с таким логином уже существует")

async def update_user_auth_token(user_id: str, token: str):
    """Обновляет токен авторизации (для 'запомнить меня')"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET auth_token = ? WHERE user_id = ?", (token, user_id))
        await db.commit()

async def get_user_by_auth_token(token: str):
    """Получает пользователя по токену авторизации"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE auth_token = ?", (token,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

async def get_user_by_username_or_id(login: str):
    """Находит пользователя по логину (username) или ТГ ID"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Сначала ищем по username, потом по user_id
        async with db.execute(
            "SELECT * FROM users WHERE username = ? OR user_id = ?", 
            (login.lower(), login)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def username_available(new_username: str, exclude_user_id: str) -> bool:
    """Проверяет, свободен ли логин (никто, кроме exclude_user_id, им не пользуется)."""
    uname = new_username.strip().lower()
    if not uname:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM users WHERE username = ? AND user_id != ?",
            (uname, exclude_user_id),
        ) as cur:
            row = await cur.fetchone()
            return row is None


async def update_user_username(user_id: str, new_username: str):
    """Обновляет логин пользователя. user_id и telegram_id не меняются."""
    uname = new_username.strip().lower()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET username = ? WHERE user_id = ?",
            (uname, user_id),
        )
        await db.commit()


async def update_user_password(user_id: str, new_password_hash: str):
    """Обновляет пароль пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET password_hash = ? WHERE user_id = ?",
            (new_password_hash, user_id),
        )
        await db.commit()


async def link_telegram_create_state(user_id: str) -> str:
    """Создаёт state для привязки Telegram. Очищает устаревшие записи. Возвращает state."""
    state = secrets.token_hex(16)
    now = int(time.time())
    cutoff = now - 15 * 60  # 15 минут
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM link_telegram_states WHERE created_at < ?", (cutoff,))
        await db.execute(
            "INSERT INTO link_telegram_states (state, user_id, created_at) VALUES (?, ?, ?)",
            (state, user_id, now)
        )
        await db.commit()
    return state


async def link_telegram_consume_state(state: str):
    """Возвращает user_id по state и удаляет запись. None если не найден или устарел."""
    cutoff = int(time.time()) - 15 * 60
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id FROM link_telegram_states WHERE state = ? AND created_at >= ?",
            (state, cutoff)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        user_id = row[0]
        await db.execute("DELETE FROM link_telegram_states WHERE state = ?", (state,))
        await db.commit()
        return user_id


async def get_user_by_telegram_id(telegram_id: str):
    """Возвращает пользователя по telegram_id (старая логика, напрямую из users)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def _get_user_by_telegram_id_or_user_id_legacy(telegram_id: str):
    """
    Старая логика: сначала ищет по telegram_id (привязанный веб), иначе по user_id (TG-only).
    Используется как fallback в новой схеме.
    """
    user = await get_user_by_telegram_id(telegram_id)
    if user:
        return user
    return await get_user_by_id(telegram_id)


async def get_user_by_telegram_id_v2(telegram_id: str, use_fallback: bool = True):
    """
    Новая логика поиска пользователя по Telegram ID.

    1. Ищет в telegram_links (telegram_id -> users.user_id).
    2. Если не найдено и use_fallback=True - использует старую логику
       (_get_user_by_telegram_id_or_user_id_legacy).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # 1. Ищем связь в telegram_links
        async with db.execute(
            """
            SELECT u.*
            FROM telegram_links tl
            JOIN users u ON u.user_id = tl.user_id
            WHERE tl.telegram_id = ?
            """,
            (telegram_id,),
        ) as cur:
            row = await cur.fetchone()
            if row:
                return dict(row)

    # 2. Fallback на старую схему, если включен
    if use_fallback:
        return await _get_user_by_telegram_id_or_user_id_legacy(telegram_id)

    return None


async def create_telegram_link(telegram_id: str, user_id: str):
    """Создаёт или обновляет связь TG ↔ аккаунт и помечает TG как известный."""
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO telegram_links (telegram_id, user_id, linked_at)
            VALUES (?, ?, ?)
            """,
            (telegram_id, user_id, now),
        )
        # Помечаем TG как известный (если ещё не был)
        await db.execute(
            """
            INSERT OR IGNORE INTO known_telegram_ids (telegram_id, first_seen_at)
            VALUES (?, ?)
            """,
            (telegram_id, now),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Единая логика привязки TG: один аккаунт на один Telegram, без сирот и дублей
# ---------------------------------------------------------------------------

async def merge_user_into_target(source_user_id: str, target_user_id: str) -> bool:
    """
    Переносит все данные с аккаунта source_user_id на аккаунт target_user_id
    и удаляет исходный аккаунт. Используется при перепривязке TG к другому аккаунту.

    Таблицы: subscriptions (subscriber_id), payments, promo_code_uses,
    sent_notifications, link_telegram_states.
    После переноса удаляется запись source из users.

    Returns:
        True если перенос выполнен, False если source == target или пользователь не найден.
    """
    if source_user_id == target_user_id:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, user_id FROM users WHERE user_id IN (?, ?)",
                (source_user_id, target_user_id),
            ) as cur:
                rows = await cur.fetchall()
            by_uid = {r["user_id"]: r["id"] for r in rows}
            source_id = by_uid.get(source_user_id)
            target_id = by_uid.get(target_user_id)
            if not source_id or not target_id:
                logger.warning(
                    f"merge_user_into_target: пользователь не найден "
                    f"source={source_user_id} (id={source_id}), target={target_user_id} (id={target_id})"
                )
                return False
            await db.execute("BEGIN TRANSACTION")
            # Подписки: переносим на целевого пользователя по subscriber_id (users.id)
            await db.execute(
                "UPDATE subscriptions SET subscriber_id = ? WHERE subscriber_id = ?",
                (target_id, source_id),
            )
            # Платежи и прочее по user_id (текст)
            await db.execute(
                "UPDATE payments SET user_id = ? WHERE user_id = ?",
                (target_user_id, source_user_id),
            )
            await db.execute(
                "UPDATE promo_code_uses SET user_id = ? WHERE user_id = ?",
                (target_user_id, source_user_id),
            )
            await db.execute(
                "UPDATE sent_notifications SET user_id = ? WHERE user_id = ?",
                (target_user_id, source_user_id),
            )
            await db.execute(
                "UPDATE link_telegram_states SET user_id = ? WHERE user_id = ?",
                (target_user_id, source_user_id),
            )
            # Удаляем связь telegram_links для source (если осталась — при перепривязке уже заменили на target)
            await db.execute(
                "DELETE FROM telegram_links WHERE user_id = ?",
                (source_user_id,),
            )
            # Модуль событий: переносим рефералы и засчитанные оплаты с source на target
            async with db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='event_referrals'"
            ) as cur:
                if await cur.fetchone():
                    await db.execute(
                        "UPDATE event_referrals SET referrer_user_id = ? WHERE referrer_user_id = ?",
                        (target_user_id, source_user_id),
                    )
                    # Удаляем рефералы source, где target уже приглашён в том же событии (UNIQUE)
                    await db.execute(
                        """DELETE FROM event_referrals WHERE referred_user_id = ? AND event_id IN
                           (SELECT event_id FROM event_referrals WHERE referred_user_id = ?)""",
                        (source_user_id, target_user_id),
                    )
                    await db.execute(
                        "UPDATE event_referrals SET referred_user_id = ? WHERE referred_user_id = ?",
                        (target_user_id, source_user_id),
                    )
            async with db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='event_counted_payments'"
            ) as cur:
                if await cur.fetchone():
                    await db.execute(
                        """DELETE FROM event_counted_payments WHERE referred_user_id = ? AND event_id IN
                           (SELECT event_id FROM event_counted_payments WHERE referred_user_id = ?)""",
                        (source_user_id, target_user_id),
                    )
                    await db.execute(
                        "UPDATE event_counted_payments SET referred_user_id = ? WHERE referred_user_id = ?",
                        (target_user_id, source_user_id),
                    )
            async with db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_referral_codes'"
            ) as cur:
                if await cur.fetchone():
                    await db.execute(
                        "DELETE FROM user_referral_codes WHERE user_id = ?",
                        (source_user_id,),
                    )
            await db.execute("DELETE FROM users WHERE id = ?", (source_id,))
            await db.commit()
            logger.info(
                f"Аккаунт {source_user_id} объединён с {target_user_id}: данные перенесены, старый аккаунт удалён."
            )
            return True
        except Exception as e:
            await db.rollback()
            logger.error(f"Ошибка merge_user_into_target {source_user_id} -> {target_user_id}: {e}", exc_info=True)
            raise


async def link_telegram_to_account(telegram_id: str, target_user_id: str) -> dict:
    """
    Единая точка привязки Telegram к аккаунту (target_user_id).
    Если этот TG был привязан к другому аккаунту (например TG-first) — переносит все данные
    на target и удаляет старый аккаунт (без сирот и дублей).

    Returns:
        {"merged": bool, "previous_user_id": str | None}
    """
    result = {"merged": False, "previous_user_id": None}
    existing = await get_telegram_link(telegram_id)
    previous_owner = None
    if existing and existing.get("user_id") != target_user_id:
        previous_owner = existing["user_id"]
    # Сначала переводим связь на целевой аккаунт (чтобы telegram_links не указывал на source)
    await create_telegram_link(telegram_id, target_user_id)
    await update_user_telegram_id(target_user_id, telegram_id)
    if previous_owner:
        await merge_user_into_target(previous_owner, target_user_id)
        result["merged"] = True
        result["previous_user_id"] = previous_owner
    await mark_telegram_id_known(telegram_id)
    return result


async def rename_user_id(old_user_id: str, new_user_id: str) -> bool:
    """
    Меняет user_id пользователя во всех связанных таблицах.
    Используется при отвязке TG-first аккаунта для превращения его в полноценный веб-аккаунт.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("BEGIN TRANSACTION")
            
            # 1. Основная таблица пользователей
            await db.execute(
                "UPDATE users SET user_id = ? WHERE user_id = ?",
                (new_user_id, old_user_id)
            )
            
            # 2. Платежи
            await db.execute(
                "UPDATE payments SET user_id = ? WHERE user_id = ?",
                (new_user_id, old_user_id)
            )
            
            # 3. Уведомления
            await db.execute(
                "UPDATE sent_notifications SET user_id = ? WHERE user_id = ?",
                (new_user_id, old_user_id)
            )
            
            # 4. Состояния привязки
            await db.execute(
                "UPDATE link_telegram_states SET user_id = ? WHERE user_id = ?",
                (new_user_id, old_user_id)
            )
            
            # 5. Использование промокодов
            await db.execute(
                "UPDATE promo_code_uses SET user_id = ? WHERE user_id = ?",
                (new_user_id, old_user_id)
            )

            # 6. Связи Telegram (на всякий случай, если запись еще не удалена)
            await db.execute(
                "UPDATE telegram_links SET user_id = ? WHERE user_id = ?",
                (new_user_id, old_user_id)
            )

            # 7. Модуль событий (event_referrals, event_counted_payments, user_referral_codes)
            async with db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='event_referrals'"
            ) as cur:
                if await cur.fetchone():
                    await db.execute(
                        "UPDATE event_referrals SET referrer_user_id = ? WHERE referrer_user_id = ?",
                        (new_user_id, old_user_id)
                    )
                    await db.execute(
                        "UPDATE event_referrals SET referred_user_id = ? WHERE referred_user_id = ?",
                        (new_user_id, old_user_id)
                    )
            async with db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='event_counted_payments'"
            ) as cur:
                if await cur.fetchone():
                    await db.execute(
                        "UPDATE event_counted_payments SET referred_user_id = ? WHERE referred_user_id = ?",
                        (new_user_id, old_user_id)
                    )
            async with db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_referral_codes'"
            ) as cur:
                if await cur.fetchone():
                    await db.execute(
                        "UPDATE user_referral_codes SET user_id = ? WHERE user_id = ?",
                        (new_user_id, old_user_id)
                    )

            await db.commit()
            logger.info(f"User ID успешно изменен с {old_user_id} на {new_user_id}")
            return True
        except Exception as e:
            await db.rollback()
            logger.error(f"Ошибка при переименовании user_id {old_user_id} -> {new_user_id}: {e}")
            raise e


async def delete_telegram_link(telegram_id: str):
    """Удаляет связь TG ↔ аккаунт (используется при отвязке)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM telegram_links WHERE telegram_id = ?", (telegram_id,))
        await db.commit()


async def get_telegram_link(telegram_id: str):
    """Возвращает запись из telegram_links по telegram_id."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM telegram_links WHERE telegram_id = ?", (telegram_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def is_known_telegram_id(telegram_id: str) -> bool:
    """Проверяет, известен ли Telegram ID (для контроля выдачи триала)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM known_telegram_ids WHERE telegram_id = ? LIMIT 1",
            (telegram_id,),
        ) as cur:
            row = await cur.fetchone()
            return row is not None


async def mark_telegram_id_known(telegram_id: str):
    """Помечает Telegram ID как известный (без изменения существующей даты)."""
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO known_telegram_ids (telegram_id, first_seen_at)
            VALUES (?, ?)
            """,
            (telegram_id, now),
        )
        await db.commit()


async def update_user_telegram_id(user_id: str, telegram_id: str | None):
    """
    Устанавливает или сбрасывает telegram_id у пользователя (поле в users).

    Связь в telegram_links создаётся/удаляется отдельными функциями
    create_telegram_link/delete_telegram_link, чтобы явно контролировать поведение.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET telegram_id = ? WHERE user_id = ?",
            (telegram_id, user_id),
        )
        await db.commit()


async def get_telegram_chat_id_for_notification(user_id: str) -> int | None:
    """
    Возвращает chat_id для отправки в Telegram.
    Единый источник: сначала telegram_links (user_id -> telegram_id), затем fallback на users.telegram_id и числовой user_id.
    """
    # 1. telegram_links — каноническая связь user_id -> telegram_id
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT telegram_id FROM telegram_links WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            if row is not None:
                try:
                    return int(row[0])
                except (TypeError, ValueError):
                    pass
    # 2. Fallback: users.telegram_id и числовой user_id (legacy TG-first)
    user = await get_user_by_id(user_id)
    if not user:
        return None
    tid = user.get("telegram_id")
    if tid:
        try:
            return int(tid)
        except (TypeError, ValueError):
            pass
    uid = user.get("user_id")
    if uid and isinstance(uid, str) and uid.isdigit():
        return int(uid)
    return None


async def get_subscription_conversion_data(days: int = 30):
    """
    Возвращает данные о конверсии пробных подписок в купленные
    
    Args:
        days: Количество дней для анализа
    
    Returns:
        dict: {
            'total_trial_users': int,        # Всего пользователей с пробными подписками
            'converted_users': int,          # Пользователей, которые купили после пробной
            'conversion_rate': float,        # Процент конверсии
            'daily': [                       # Ежедневная статистика
                {
                    'date': str,
                    'trial_users': int,
                    'converted': int,
                    'conversion_rate': float
                },
                ...
            ]
        }
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        now = int(datetime.datetime.now().timestamp())
        start_timestamp = now - (days * 24 * 60 * 60)
        
        # Находим всех пользователей с пробными подписками
        async with db.execute("""
            SELECT DISTINCT subscriber_id
            FROM subscriptions
            WHERE (status = 'trial' OR price = 0)
            AND created_at >= ?
        """, (start_timestamp,)) as cur:
            trial_user_ids = [row['subscriber_id'] for row in await cur.fetchall()]
        
        if not trial_user_ids:
            return {
                'total_trial_users': 0,
                'converted_users': 0,
                'conversion_rate': 0.0,
                'daily': []
            }
        
        # Проверяем, сколько из них купили подписку
        placeholders = ','.join(['?'] * len(trial_user_ids))
        async with db.execute(f"""
            SELECT COUNT(DISTINCT subscriber_id) as count
            FROM subscriptions
            WHERE subscriber_id IN ({placeholders})
            AND status IN ('active', 'expired')
            AND status != 'trial'
            AND price > 0
        """, trial_user_ids) as cur:
            row = await cur.fetchone()
            converted_users = row['count'] if row else 0
        
        total_trial_users = len(trial_user_ids)
        conversion_rate = (converted_users / total_trial_users * 100) if total_trial_users > 0 else 0.0
        
        # Ежедневная статистика (упрощенная версия)
        daily = []
        start_date = datetime.datetime.fromtimestamp(start_timestamp).date()
        end_date = datetime.datetime.now().date()
        
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            date_timestamp = int(datetime.datetime.combine(current_date, datetime.time.min).timestamp())
            next_date_timestamp = date_timestamp + 86400
            
            # Пробные подписки, созданные в этот день
            async with db.execute("""
                SELECT COUNT(DISTINCT subscriber_id) as count
                FROM subscriptions
                WHERE (status = 'trial' OR price = 0)
                AND created_at >= ? AND created_at < ?
            """, (date_timestamp, next_date_timestamp)) as cur:
                row = await cur.fetchone()
                trial_users = row['count'] if row else 0
            
            # Конверсия для этих пользователей (упрощенно - проверяем, купили ли они в течение 7 дней)
            if trial_users > 0:
                async with db.execute(f"""
                    SELECT COUNT(DISTINCT s1.subscriber_id) as count
                    FROM subscriptions s1
                    WHERE s1.subscriber_id IN (
                        SELECT DISTINCT subscriber_id
                        FROM subscriptions
                        WHERE (status = 'trial' OR price = 0)
                        AND created_at >= ? AND created_at < ?
                    )
                    AND EXISTS (
                        SELECT 1 FROM subscriptions s2
                        WHERE s2.subscriber_id = s1.subscriber_id
                        AND s2.status IN ('active', 'expired')
                        AND s2.status != 'trial'
                        AND s2.price > 0
                        AND s2.created_at >= ? AND s2.created_at < ?
                    )
                """, (date_timestamp, next_date_timestamp, date_timestamp, next_date_timestamp + 7*86400)) as cur:
                    row = await cur.fetchone()
                    converted = row['count'] if row else 0
            else:
                converted = 0
            
            conversion_rate_daily = (converted / trial_users * 100) if trial_users > 0 else 0.0
            
            daily.append({
                'date': date_str,
                'trial_users': trial_users,
                'converted': converted,
                'conversion_rate': round(conversion_rate_daily, 2)
            })
            
            current_date += datetime.timedelta(days=1)
        
        return {
            'total_trial_users': total_trial_users,
            'converted_users': converted_users,
            'conversion_rate': round(conversion_rate, 2),
            'daily': daily
        }

async def get_revenue_trend_data(days: int = 30):
    """
    Возвращает динамику дохода по дням за указанный период
    
    Args:
        days: Количество дней для анализа
    
    Returns:
        list: [
            {
                'date': str,              # Дата в формате YYYY-MM-DD
                'revenue': float,         # Доход за день
                'payments_count': int     # Количество успешных платежей
            },
            ...
        ]
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        now = int(datetime.datetime.now().timestamp())
        start_timestamp = now - (days * 24 * 60 * 60)
        
        # Получаем успешные платежи за период
        async with db.execute("""
            SELECT 
                created_at,
                DATE(datetime(created_at, 'unixepoch')) as date,
                meta
            FROM payments
            WHERE status = 'succeeded'
            AND created_at >= ?
            ORDER BY created_at
        """, (start_timestamp,)) as cur:
            rows = await cur.fetchall()
        
        # Группируем по датам
        daily_revenue = {}
        
        for row in rows:
            date_str = row['date']
            if date_str not in daily_revenue:
                daily_revenue[date_str] = {
                    'revenue': 0.0,
                    'payments_count': 0
                }
            
            # Извлекаем сумму из meta
            meta = row['meta']
            if meta:
                try:
                    meta_dict = json.loads(meta) if isinstance(meta, str) else meta
                    amount = meta_dict.get('amount') or meta_dict.get('price', 0)
                    if isinstance(amount, str):
                        try:
                            amount = float(amount)
                        except (ValueError, TypeError):
                            amount = 0
                    if isinstance(amount, (int, float)) and amount > 0:
                        daily_revenue[date_str]['revenue'] += amount
                        daily_revenue[date_str]['payments_count'] += 1
                except Exception:
                    pass
        
        # Преобразуем в список и заполняем пропущенные даты
        result = []
        start_date = datetime.datetime.fromtimestamp(start_timestamp).date()
        end_date = datetime.datetime.now().date()
        
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            if date_str in daily_revenue:
                result.append({
                    'date': date_str,
                    'revenue': round(daily_revenue[date_str]['revenue'], 2),
                    'payments_count': daily_revenue[date_str]['payments_count']
                })
            else:
                result.append({
                    'date': date_str,
                    'revenue': 0.0,
                    'payments_count': 0
                })
            current_date += datetime.timedelta(days=1)
        
        return result
