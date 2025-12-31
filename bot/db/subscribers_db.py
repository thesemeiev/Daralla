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
            # Короткие ключи (для обратной совместимости)
            'total': total_subscriptions,
            'active': active_subscriptions,
            'expired': expired_subscriptions,
            'trial': trial_subscriptions,
            # Длинные ключи (для читаемости кода)
            'total_subscriptions': total_subscriptions,
            'active_subscriptions': active_subscriptions,
            'expired_subscriptions': expired_subscriptions,
            'trial_subscriptions': trial_subscriptions,
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
            
            # Получаем средние значения за последние 24 часа
            averages = await get_server_load_averages(period_hours=24)
            server_avg = averages.get(server_name, {})
            
            # Рассчитываем процент загрузки (если есть лимит активных клиентов)
            # Для capacity planning можно использовать total_active как максимальную емкость
            load_percentage = 0
            if total_active > 0:
                load_percentage = round((server_avg.get('avg_online', 0) / total_active) * 100, 1)
            
            server_data.append({
                'server_name': server_name,
                'online_clients': online_count,  # Текущее значение
                'total_active': total_active,
                'offline_clients': offline_count,
                'avg_online_24h': server_avg.get('avg_online', 0),  # Среднее за 24 часа
                'max_online_24h': server_avg.get('max_online', 0),  # Максимум за 24 часа
                'min_online_24h': server_avg.get('min_online', 0),  # Минимум за 24 часа
                'samples_24h': server_avg.get('samples', 0),  # Количество измерений
                'load_percentage': load_percentage  # Процент загрузки канала
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
        
        # Активные подписки на 1 месяц
        async with db.execute("""
            SELECT COUNT(*) as count 
            FROM subscriptions 
            WHERE status = 'active' 
            AND period = 'month'
        """) as cur:
            row = await cur.fetchone()
            month_active = row['count'] if row else 0
        
        # Активные подписки на 3 месяца
        async with db.execute("""
            SELECT COUNT(*) as count 
            FROM subscriptions 
            WHERE status = 'active' 
            AND period = '3month'
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
        
        # Получаем все подписки, созданные или активные в период
        async with db.execute("""
            SELECT 
                created_at,
                DATE(datetime(created_at, 'unixepoch')) as date,
                status,
                price,
                period,
                expires_at
            FROM subscriptions
            WHERE created_at >= ? OR expires_at >= ?
            ORDER BY created_at
        """, (start_timestamp, start_timestamp)) as cur:
            rows = await cur.fetchall()
        
        # Группируем по датам
        daily_data = {}
        
        for row in rows:
            date_str = row['date']
            if date_str not in daily_data:
                daily_data[date_str] = {
                    'trial_active': 0,
                    'purchased_active': 0,
                    'trial_created': 0,
                    'purchased_created': 0
                }
            
            # Определяем тип подписки
            is_trial = row['status'] == 'trial' or row['price'] == 0
            is_active = row['status'] == 'active'
            created_timestamp = row['created_at']
            
            # Если подписка была создана в этот день
            if created_timestamp >= start_timestamp:
                if is_trial:
                    daily_data[date_str]['trial_created'] += 1
                else:
                    daily_data[date_str]['purchased_created'] += 1
            
            # Если подписка активна в этот день
            if is_active:
                if is_trial:
                    daily_data[date_str]['trial_active'] += 1
                else:
                    daily_data[date_str]['purchased_active'] += 1
        
        # Преобразуем в список и заполняем пропущенные даты
        result = []
        start_date = datetime.datetime.fromtimestamp(start_timestamp).date()
        end_date = datetime.datetime.now().date()
        
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            if date_str in daily_data:
                result.append({
                    'date': date_str,
                    **daily_data[date_str]
                })
            else:
                result.append({
                    'date': date_str,
                    'trial_active': 0,
                    'purchased_active': 0,
                    'trial_created': 0,
                    'purchased_created': 0
                })
            current_date += datetime.timedelta(days=1)
        
        return result

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
