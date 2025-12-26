"""
Модуль работы с пользователями и их подписками
"""
import aiosqlite
import datetime
import logging
import uuid
from . import DB_PATH

logger = logging.getLogger(__name__)

async def init_subscribers_db():
    """Инициализирует таблицы пользователей и подписок в единой БД"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Единая таблица пользователей (бывшие users + subscribers)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT UNIQUE NOT NULL,
                first_seen INTEGER NOT NULL,
                last_seen INTEGER NOT NULL
            )
        """)

        # Таблица подписок
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscriber_id INTEGER NOT NULL,
                status TEXT NOT NULL,          -- active, expired, canceled
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
        
        await db.commit()

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

async def create_subscription(subscriber_id: int, period: str, device_limit: int, price: float, expires_at: int, name: str = None):
    """Создаёт новую подписку"""
    token = uuid.uuid4().hex[:24]
    now = int(datetime.datetime.now().timestamp())
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """INSERT INTO subscriptions 
               (subscriber_id, status, period, device_limit, created_at, expires_at, subscription_token, price, name)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (subscriber_id, 'active', period, device_limit, now, expires_at, token, price, name)
        ) as cur:
            sub_id = cur.lastrowid
            await db.commit()
            return sub_id, token

async def get_all_active_subscriptions():
    """Возвращает все активные подписки"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT s.*, u.user_id 
               FROM subscriptions s 
               JOIN users u ON s.subscriber_id = u.id 
               WHERE s.status = 'active'"""
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
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE subscriptions SET expires_at = ? WHERE id = ?", (new_expires_at, subscription_id))
        await db.commit()

async def update_subscription_device_limit(subscription_id: int, new_device_limit: int):
    """Обновляет лимит устройств/IP для подписки"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE subscriptions SET device_limit = ? WHERE id = ?", (new_device_limit, subscription_id))
        await db.commit()

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
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO subscription_servers (subscription_id, server_name, client_email, client_id) VALUES (?, ?, ?, ?)",
            (subscription_id, server_name, client_email, client_id)
        )
        await db.commit()

async def remove_subscription_server(subscription_id: int, server_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM subscription_servers WHERE subscription_id = ? AND server_name = ?", (subscription_id, server_name))
        await db.commit()
        return True

async def get_subscription_statistics():
    """Возвращает статистику по подпискам и пользователям"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
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
        
        # Количество отмененных подписок
        async with db.execute("SELECT COUNT(*) as count FROM subscriptions WHERE status = 'canceled'") as cur:
            row = await cur.fetchone()
            canceled_subscriptions = row['count'] if row else 0
        
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
        
        return {
            'total_users': total_users,
            'users_with_active_subs': users_with_active_subs,
            'total': total_subscriptions,
            'active': active_subscriptions,
            'expired': expired_subscriptions,
            'canceled': canceled_subscriptions,
            'trial': trial_subscriptions,
            'total_server_clients': total_server_clients,
            'active_server_clients': active_server_clients
        }

async def get_user_by_id(user_id: str):
    """Возвращает информацию о пользователе по user_id"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

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
            from ... import bot as bot_module
            return getattr(bot_module, 'server_manager', None)
        except (ImportError, AttributeError):
            return None
    
    server_manager = get_server_manager()
    if not server_manager:
        logger.warning("server_manager недоступен, возвращаем пустые данные")
        return []
    
    server_data = []
    
    # Проходим по всем серверам
    for server in server_manager.servers:
        server_name = server["name"]
        xui = server.get("x3")
        
        if not xui:
            # Сервер недоступен
            server_data.append({
                'server_name': server_name,
                'online_clients': 0,
                'total_active': 0,
                'offline_clients': 0
            })
            continue
        
        try:
            # Получаем количество онлайн клиентов с сервера
            total_active, online_count, offline_count = xui.get_online_clients_count()
            
            server_data.append({
                'server_name': server_name,
                'online_clients': online_count,
                'total_active': total_active,
                'offline_clients': offline_count
            })
        except Exception as e:
            logger.error(f"Ошибка получения данных о нагрузке с сервера {server_name}: {e}")
            server_data.append({
                'server_name': server_name,
                'online_clients': 0,
                'total_active': 0,
                'offline_clients': 0
            })
    
    # Сортируем по количеству онлайн клиентов
    server_data.sort(key=lambda x: x['online_clients'], reverse=True)
    
    return server_data

# ==================== ПРОМОКОДЫ ====================

async def create_promo_code(code: str, promo_type: str, period: str, max_uses: int = 1, expires_at: int = None):
    """Создает новый промокод"""
    now = int(datetime.datetime.now().timestamp())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO promo_codes (code, type, period, max_uses, expires_at, is_active, created_at)
            VALUES (?, ?, ?, ?, ?, 1, ?)
        """, (code.upper(), promo_type, period, max_uses, expires_at, now))
        await db.commit()
        logger.info(f"Создан промокод: {code} (type={promo_type}, period={period})")

async def get_promo_code(code: str):
    """Получает промокод по коду"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM promo_codes WHERE code = ? AND is_active = 1
        """, (code.upper(),)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

async def check_promo_code_valid(code: str, user_id: str, promo_type: str):
    """
    Проверяет валидность промокода для пользователя
    Returns: (is_valid: bool, error_message: str, promo_data: dict)
    
    УСТАРЕЛО: Теперь используется проверка активного промокода из конфигурации.
    Оставлено для обратной совместимости.
    """
    promo = await get_promo_code(code)
    
    if not promo:
        return False, "Промокод не найден", None
    
    # Проверяем срок действия
    if promo['expires_at'] and promo['expires_at'] < int(datetime.datetime.now().timestamp()):
        return False, "Промокод истек", None
    
    # Проверяем лимит использований
    if promo['max_uses'] > 0 and promo['uses_count'] >= promo['max_uses']:
        return False, "Промокод уже использован максимальное количество раз", None
    
    # УБРАНО: Проверка на повторное использование одним пользователем
    
    return True, None, dict(promo)

async def use_promo_code(code: str, user_id: str, subscription_id: int = None):
    """
    Отмечает промокод как использованный.
    Увеличивает счетчик использований, но не блокирует повторное использование одним пользователем.
    """
    promo = await get_promo_code(code)
    if not promo:
        # Промокод не найден в БД - это нормально, если он только в конфигурации
        logger.warning(f"Промокод {code} не найден в БД при попытке отметить использование")
        return False
    
    now = int(datetime.datetime.now().timestamp())
    async with aiosqlite.connect(DB_PATH) as db:
        # Увеличиваем счетчик использований (не проверяем лимит - промокод может использоваться многократно)
        await db.execute("""
            UPDATE promo_codes SET uses_count = uses_count + 1 WHERE id = ?
        """, (promo['id'],))
        
        # Записываем использование (для статистики, но не блокируем повторное использование)
        await db.execute("""
            INSERT INTO promo_code_uses (promo_code_id, user_id, subscription_id, used_at)
            VALUES (?, ?, ?, ?)
        """, (promo['id'], user_id, subscription_id, now))
        
        await db.commit()
        logger.info(f"Промокод {code} использован пользователем {user_id}, subscription_id={subscription_id}")
        return True

async def delete_promo_code(code: str):
    """Удаляет промокод из БД (помечает как неактивный)"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE promo_codes SET is_active = 0 WHERE code = ?
        """, (code.upper(),))
        await db.commit()
        logger.info(f"Промокод {code} удален (помечен как неактивный)")

async def get_all_promo_codes():
    """Получает все активные промокоды"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM promo_codes WHERE is_active = 1 ORDER BY created_at DESC
        """) as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

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
