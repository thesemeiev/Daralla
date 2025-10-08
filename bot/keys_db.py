import aiosqlite
import asyncio
import json
import logging
import datetime
import os

# Определяем путь к базам данных относительно корневой папки проекта
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
# Создаем папку data если её нет
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, 'vpn_keys.db')
REFERRAL_DB_PATH = os.path.join(DATA_DIR, 'referral_system.db')
logger = logging.getLogger(__name__)

async def get_all_user_ids(min_last_seen: int = None) -> list:
    """Возвращает список всех user_id из таблицы users.
    Если передан min_last_seen (unix ts), вернёт только тех, кто был активен после этой даты.
    """
    try:
        async with aiosqlite.connect(REFERRAL_DB_PATH) as db:
            if min_last_seen is not None:
                async with db.execute('SELECT user_id FROM users WHERE last_seen >= ? ORDER BY last_seen DESC', (min_last_seen,)) as cur:
                    rows = await cur.fetchall()
            else:
                async with db.execute('SELECT user_id FROM users ORDER BY last_seen DESC') as cur:
                    rows = await cur.fetchall()
            return [row[0] for row in rows]
    except Exception as e:
        logger.error(f"GET_ALL_USER_IDS error: {e}")
        return []
async def register_simple_user(user_id: str):
    """Регистрирует пользователя в таблице users (upsert)."""
    try:
        now = int(datetime.datetime.now().timestamp())
        async with aiosqlite.connect(REFERRAL_DB_PATH) as db:
            await db.execute('''
                INSERT INTO users (user_id, first_seen, last_seen)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET last_seen = excluded.last_seen
            ''', (user_id, now, now))
            await db.commit()
    except Exception as e:
        logger.error(f"REGISTER_SIMPLE_USER: error user_id={user_id}: {e}")

async def is_known_user(user_id: str) -> bool:
    """Проверяет наличие user_id в таблице users."""
    try:
        async with aiosqlite.connect(REFERRAL_DB_PATH) as db:
            async with db.execute('SELECT 1 FROM users WHERE user_id = ? LIMIT 1', (user_id,)) as cursor:
                return (await cursor.fetchone()) is not None
    except Exception as e:
        logger.error(f"IS_KNOWN_USER error for user_id={user_id}: {e}")
        return False

async def init_payments_db():
    logger.info(f"INIT_PAYMENTS_DB: Начинаем инициализацию базы данных по пути {DB_PATH}")
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            logger.info("INIT_PAYMENTS_DB: Подключение к базе данных успешно")
            await db.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    user_id TEXT,
                    payment_id TEXT PRIMARY KEY,
                    status TEXT,
                    created_at INTEGER,
                    meta TEXT,
                    activated INTEGER DEFAULT 0
                )
            ''')
            logger.info("INIT_PAYMENTS_DB: Таблица payments создана/проверена")
            await db.commit()
            logger.info("INIT_PAYMENTS_DB: Изменения зафиксированы")
    except Exception as e:
        logger.error(f"INIT_PAYMENTS_DB: Ошибка при инициализации: {e}")
        raise

async def add_payment(user_id: str, payment_id: str, status: str, created_at: int, meta: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT OR REPLACE INTO payments (user_id, payment_id, status, created_at, meta, activated)
            VALUES (?, ?, ?, ?, ?, COALESCE((SELECT activated FROM payments WHERE payment_id = ?), 0))
        ''', (user_id, payment_id, status, created_at, json.dumps(meta), payment_id))
        await db.commit()
    logger.info(f"Платёж добавлен: user_id={user_id}, payment_id={payment_id}, status={status}")

async def get_payment(user_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('''
            SELECT user_id, payment_id, status, created_at, meta, activated
            FROM payments
            WHERE user_id = ?
            ORDER BY created_at DESC LIMIT 1
        ''', (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    'user_id': row[0],
                    'payment_id': row[1],
                    'status': row[2],
                    'created_at': row[3],
                    'meta': json.loads(row[4]) if row[4] else {},
                    'activated': bool(row[5])
                }
            return None

async def get_payment_by_id(payment_id: str) -> dict | None:
    """Получает платеж по payment_id (для webhook'ов)"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('''
            SELECT user_id, payment_id, status, created_at, meta, activated
            FROM payments
            WHERE payment_id = ?
        ''', (payment_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    'user_id': row[0],
                    'payment_id': row[1],
                    'status': row[2],
                    'created_at': row[3],
                    'meta': json.loads(row[4]) if row[4] else {},
                    'activated': bool(row[5])
                }
            return None

async def update_payment_status(payment_id: str, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE payments SET status = ? WHERE payment_id = ?', (status, payment_id))
        await db.commit()
    logger.info(f"Статус платежа обновлён: payment_id={payment_id}, status={status}")

async def mark_payment_as_activated(payment_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE payments SET activated = 1 WHERE payment_id = ?', (payment_id,))
        await db.commit()
    logger.info(f"Платёж помечен как активированный: payment_id={payment_id}")

async def get_all_pending_payments() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('''
            SELECT user_id, payment_id, status, created_at, meta, activated
            FROM payments
            WHERE status = ?
        ''', ('pending',)) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    'user_id': row[0],
                    'payment_id': row[1],
                    'status': row[2],
                    'created_at': row[3],
                    'meta': json.loads(row[4]) if row[4] else {},
                    'activated': bool(row[5])
                } for row in rows
            ]

async def get_pending_payment(user_id: str, period: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('''
            SELECT user_id, payment_id, status, created_at, meta, activated
            FROM payments
            WHERE user_id = ? AND status = ? AND json_extract(meta, '$.period') = ?
            ORDER BY created_at DESC LIMIT 1
        ''', (user_id, 'pending', period)) as cursor:
            row = await cursor.fetchone()
            if row:
                return {
                    'user_id': row[0],
                    'payment_id': row[1],
                    'status': row[2],
                    'created_at': row[3],
                    'meta': json.loads(row[4]) if row[4] else {},
                    'activated': bool(row[5])
                }
            return None

# Для теста
if __name__ == '__main__':
    asyncio.run(init_payments_db())

async def cleanup_old_payments(days_old: int = 7):
    """
    Очищает старые записи платежей из базы данных
    :param days_old: Удаляет записи старше указанного количества дней
    """
    import time
    cutoff_time = int(time.time()) - (days_old * 24 * 60 * 60)
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Удаляем старые записи
        async with db.execute('''
            DELETE FROM payments 
            WHERE created_at < ? AND status IN ('succeeded', 'canceled', 'refunded')
        ''', (cutoff_time,)) as cursor:
            deleted_count = cursor.rowcount
        
        await db.commit()
    
    logger.info(f"Очищено {deleted_count} старых записей платежей (старше {days_old} дней)")
    return deleted_count


async def cleanup_expired_pending_payments(minutes_old: int = 20):
    """
    Очищает просроченные pending платежи
    :param minutes_old: Удаляет pending платежи старше указанного количества минут
    """
    import time
    cutoff_time = int(time.time()) - (minutes_old * 60)
    
    async with aiosqlite.connect(DB_PATH) as db:
        # Удаляем просроченные pending платежи
        async with db.execute('''
            DELETE FROM payments 
            WHERE created_at < ? AND status = 'pending'
        ''', (cutoff_time,)) as cursor:
            deleted_count = cursor.rowcount
        
        await db.commit()
    
    logger.info(f"Удалено {deleted_count} просроченных pending платежей (старше {minutes_old} минут)")
    return deleted_count


# ===== РЕФЕРАЛЬНАЯ СИСТЕМА =====

async def init_referral_db():
    """Инициализирует таблицы для реферальной системы"""
    async with aiosqlite.connect(REFERRAL_DB_PATH) as db:
        # Таблица реферальных связей
        await db.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                referrer_id TEXT,
                referred_id TEXT,
                created_at INTEGER,
                reward_given INTEGER DEFAULT 0,
                payment_id TEXT,
                PRIMARY KEY (referrer_id, referred_id)
            )
        ''')
        
        # Таблица баллов пользователей
        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_points (
                user_id TEXT PRIMARY KEY,
                points INTEGER DEFAULT 0,
                total_earned INTEGER DEFAULT 0,
                total_spent INTEGER DEFAULT 0,
                last_updated INTEGER
            )
        ''')
        
        # Таблица транзакций баллов
        await db.execute('''
            CREATE TABLE IF NOT EXISTS points_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                amount INTEGER,
                type TEXT, -- 'earned', 'spent', 'refund'
                description TEXT,
                source_id TEXT,
                created_at INTEGER
            )
        ''')
        
        # Унифицированная таблица пользователей
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                first_seen INTEGER,
                last_seen INTEGER
            )
        ''')
        
        # Таблица конфигурации
        await db.execute('''
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT,
                description TEXT,
                updated_at INTEGER
            )
        ''')
        
        await db.commit()
        
        # Инициализируем дефолтные настройки
        await init_default_config()

async def prune_points_history(user_id: str, keep: int = 5):
    """Удаляет старые транзакции баллов, оставляя только последние `keep` записей для пользователя."""
    try:
        if not user_id or not isinstance(keep, int) or keep <= 0:
            return
        async with aiosqlite.connect(REFERRAL_DB_PATH) as db:
            await db.execute('''
                DELETE FROM points_transactions
                WHERE user_id = ?
                  AND id NOT IN (
                    SELECT id FROM points_transactions
                    WHERE user_id = ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT ?
                  )
            ''', (user_id, user_id, keep))
            await db.commit()
    except Exception as e:
        logger.error(f"PRUNE_POINTS_HISTORY: error for user_id={user_id}, keep={keep}: {e}")

async def init_default_config():
    """Инициализирует дефолтные настройки конфигурации"""
    try:
        async with aiosqlite.connect(REFERRAL_DB_PATH) as db:
            # Проверяем, есть ли уже настройки
            async with db.execute('SELECT COUNT(*) FROM config') as cursor:
                count = (await cursor.fetchone())[0]
            
            if count == 0:
                # Вставляем дефолтные настройки
                now = int(datetime.datetime.now().timestamp())
                await db.execute('''
                    INSERT INTO config (key, value, description, updated_at)
                    VALUES 
                        ('points_days_per_point', '14', 'Количество дней VPN за 1 балл', ?),
                        ('points_min_days', '1', 'Минимальное количество дней за балл', ?),
                        ('points_max_days', '365', 'Максимальное количество дней за балл', ?)
                ''', (now, now, now))
                await db.commit()
                logger.info("Инициализированы дефолтные настройки конфигурации")
    except Exception as e:
        logger.error(f"INIT_DEFAULT_CONFIG: error - {e}")

async def get_config(key: str, default_value: str = None) -> str:
    """Получает значение конфигурации по ключу"""
    try:
        async with aiosqlite.connect(REFERRAL_DB_PATH) as db:
            async with db.execute('SELECT value FROM config WHERE key = ?', (key,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else default_value
    except Exception as e:
        logger.error(f"GET_CONFIG: error for key={key} - {e}")
        return default_value

async def set_config(key: str, value: str, description: str = None) -> bool:
    """Устанавливает значение конфигурации"""
    try:
        now = int(datetime.datetime.now().timestamp())
        async with aiosqlite.connect(REFERRAL_DB_PATH) as db:
            await db.execute('''
                INSERT OR REPLACE INTO config (key, value, description, updated_at)
                VALUES (?, ?, ?, ?)
            ''', (key, value, description, now))
            await db.commit()
            logger.info(f"SET_CONFIG: {key} = {value}")
            return True
    except Exception as e:
        logger.error(f"SET_CONFIG: error for key={key}, value={value} - {e}")
        return False

async def get_all_config() -> dict:
    """Получает все настройки конфигурации"""
    try:
        async with aiosqlite.connect(REFERRAL_DB_PATH) as db:
            async with db.execute('SELECT key, value, description FROM config ORDER BY key') as cursor:
                rows = await cursor.fetchall()
                return {row[0]: {'value': row[1], 'description': row[2]} for row in rows}
    except Exception as e:
        logger.error(f"GET_ALL_CONFIG: error - {e}")
        return {}

async def save_referral_connection(referrer_id: str, referred_id: str, server_manager=None):
    """Сохраняет реферальную связь только если пользователь еще не был чьим-то рефералом"""
    logger.info(f"SAVE_REFERRAL_CONNECTION: referrer_id={referrer_id}, referred_id={referred_id}")
    
    try:
        # Валидация входных данных
        if not referrer_id or not referred_id:
            logger.error(f"SAVE_REFERRAL_CONNECTION: Invalid input - referrer_id={referrer_id}, referred_id={referred_id}")
            return False
        
        if referrer_id == referred_id:
            logger.warning(f"SAVE_REFERRAL_CONNECTION: User cannot refer themselves - user_id={referrer_id}")
            return False
        
        async with aiosqlite.connect(REFERRAL_DB_PATH) as db:
            # Проверяем, был ли этот пользователь уже чьим-то рефералом
            async with db.execute('''
                SELECT COUNT(*) FROM referrals WHERE referred_id = ?
            ''', (referred_id,)) as cursor:
                existing_referrals = (await cursor.fetchone())[0]
            
            # Проверяем, был ли этот пользователь уже реферером
            async with db.execute('''
                SELECT COUNT(*) FROM referrals WHERE referrer_id = ?
            ''', (referred_id,)) as cursor:
                existing_referrers = (await cursor.fetchone())[0]
            
            logger.info(f"SAVE_REFERRAL_CONNECTION: existing_referrals={existing_referrals}, existing_referrers={existing_referrers}")
            
            # Если пользователь еще не участвовал в реферальной системе, создаем связь
            if existing_referrals == 0 and existing_referrers == 0:
                await db.execute('''
                    INSERT INTO referrals (referrer_id, referred_id, created_at)
                    VALUES (?, ?, ?)
                ''', (referrer_id, referred_id, int(datetime.datetime.now().timestamp())))
                await db.commit()
                logger.info(f"SAVE_REFERRAL_CONNECTION: connection created successfully")
                return True
            else:
                # Пользователь уже участвовал в реферальной системе
                logger.info(f"SAVE_REFERRAL_CONNECTION: user already participated in referral system")
                return False
                
    except Exception as e:
        logger.error(f"SAVE_REFERRAL_CONNECTION: Critical error - {e}")
        return False

async def get_pending_referral(referred_id: str) -> str:
    """Получает реферера для пользователя, который еще не получил награду"""
    try:
        if not referred_id:
            logger.error(f"GET_PENDING_REFERRAL: Invalid input - referred_id={referred_id}")
            return None
            
        async with aiosqlite.connect(REFERRAL_DB_PATH) as db:
            async with db.execute('''
                SELECT referrer_id FROM referrals 
                WHERE referred_id = ? AND reward_given = 0
            ''', (referred_id,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None
                
    except Exception as e:
        logger.error(f"GET_PENDING_REFERRAL: Critical error - {e}")
        return None

async def mark_referral_reward_given(referrer_id: str, referred_id: str, payment_id: str):
    """Отмечает реферальную награду как выданную"""
    try:
        if not referrer_id or not referred_id or not payment_id:
            logger.error(f"MARK_REFERRAL_REWARD_GIVEN: Invalid input - referrer_id={referrer_id}, referred_id={referred_id}, payment_id={payment_id}")
            return False
            
        async with aiosqlite.connect(REFERRAL_DB_PATH) as db:
            await db.execute('''
                UPDATE referrals 
                SET reward_given = 1, payment_id = ?
                WHERE referrer_id = ? AND referred_id = ?
            ''', (payment_id, referrer_id, referred_id))
            await db.commit()
            logger.info(f"MARK_REFERRAL_REWARD_GIVEN: Reward marked for referrer={referrer_id}, referred={referred_id}")
            return True
            
    except Exception as e:
        logger.error(f"MARK_REFERRAL_REWARD_GIVEN: Critical error - {e}")
        return False

async def add_points(user_id: str, points: int, description: str, source_id: str = None):
    """Добавляет баллы пользователю"""
    try:
        # Валидация входных данных
        if not user_id or not isinstance(points, int) or points <= 0:
            logger.error(f"ADD_POINTS: Invalid input - user_id={user_id}, points={points}")
            return False
            
        # Ограничение на максимальное количество баллов
        MAX_POINTS = 10000
        if points > MAX_POINTS:
            logger.error(f"ADD_POINTS: Points limit exceeded - user_id={user_id}, points={points}")
            return False
        
        async with aiosqlite.connect(REFERRAL_DB_PATH) as db:
            # Обновляем баланс
            await db.execute('''
                INSERT OR REPLACE INTO user_points (user_id, points, total_earned, last_updated)
                VALUES (?, 
                        COALESCE((SELECT points FROM user_points WHERE user_id = ?), 0) + ?,
                        COALESCE((SELECT total_earned FROM user_points WHERE user_id = ?), 0) + ?,
                        ?)
            ''', (user_id, user_id, points, user_id, points, int(datetime.datetime.now().timestamp())))
            
            # Записываем транзакцию
            await db.execute('''
                INSERT INTO points_transactions (user_id, amount, type, description, source_id, created_at)
                VALUES (?, ?, 'earned', ?, ?, ?)
            ''', (user_id, points, description, source_id, int(datetime.datetime.now().timestamp())))
            
            await db.commit()
            # Оставляем только последние 5 транзакций пользователя
            await prune_points_history(user_id, keep=5)
            logger.info(f"ADD_POINTS: Added {points} points to user {user_id}")
            return True
            
    except Exception as e:
        logger.error(f"ADD_POINTS: Critical error - {e}")
        return False

async def spend_points(user_id: str, points: int, description: str, source_id: str = None, bot=None) -> bool:
    """Тратит баллы пользователя. Возвращает True если успешно"""
    try:
        # Валидация входных данных
        if not user_id or not isinstance(points, int) or points <= 0:
            logger.error(f"SPEND_POINTS: Invalid input - user_id={user_id}, points={points}")
            # Уведомляем админа о некорректных данных
            if bot:
                try:
                    from .bot import notify_admin
                    await notify_admin(bot, f"🚨 Ошибка валидации при списании баллов:\nuser_id={user_id}, points={points}, description={description}")
                except Exception as e:
                    logger.error(f"Failed to notify admin about spend_points validation error: {e}")
            return False
            
        async with aiosqlite.connect(REFERRAL_DB_PATH) as db:
            # Проверяем баланс
            async with db.execute('''
                SELECT points FROM user_points WHERE user_id = ?
            ''', (user_id,)) as cursor:
                row = await cursor.fetchone()
                current_points = row[0] if row else 0
            
            if current_points < points:
                logger.warning(f"SPEND_POINTS: Insufficient balance - user_id={user_id}, current={current_points}, requested={points}")
                return False
            
            # Списываем баллы
            await db.execute('''
                UPDATE user_points 
                SET points = points - ?, 
                    total_spent = total_spent + ?,
                    last_updated = ?
                WHERE user_id = ?
            ''', (points, points, int(datetime.datetime.now().timestamp()), user_id))
            
            # Записываем транзакцию
            await db.execute('''
                INSERT INTO points_transactions (user_id, amount, type, description, source_id, created_at)
                VALUES (?, ?, 'spent', ?, ?, ?)
            ''', (user_id, points, description, source_id, int(datetime.datetime.now().timestamp())))
            
            await db.commit()
            # Оставляем только последние 5 транзакций пользователя
            await prune_points_history(user_id, keep=5)
            logger.info(f"SPEND_POINTS: Spent {points} points from user {user_id}")
            return True
            
    except Exception as e:
        logger.error(f"SPEND_POINTS: Critical error - {e}")
        # Уведомляем админа о критической ошибке
        if bot:
            try:
                from .bot import notify_admin
                await notify_admin(bot, f"🚨 Критическая ошибка при списании баллов:\nuser_id={user_id}, points={points}, description={description}\nОшибка: {str(e)}")
            except Exception as notify_e:
                logger.error(f"Failed to notify admin about spend_points critical error: {notify_e}")
        return False

async def get_user_points(user_id: str) -> dict:
    """Получает информацию о баллах пользователя"""
    try:
        if not user_id:
            logger.error(f"GET_USER_POINTS: Invalid input - user_id={user_id}")
            return {'points': 0, 'total_earned': 0, 'total_spent': 0}
            
        async with aiosqlite.connect(REFERRAL_DB_PATH) as db:
            async with db.execute('''
                SELECT points, total_earned, total_spent FROM user_points WHERE user_id = ?
            ''', (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return {
                        'points': row[0],
                        'total_earned': row[1],
                        'total_spent': row[2]
                    }
                return {'points': 0, 'total_earned': 0, 'total_spent': 0}
                
    except Exception as e:
        logger.error(f"GET_USER_POINTS: Critical error - {e}")
        return {'points': 0, 'total_earned': 0, 'total_spent': 0}

async def get_points_history(user_id: str, limit: int = 10) -> list:
    """Получает историю транзакций баллов"""
    try:
        if not user_id or not isinstance(limit, int) or limit <= 0:
            logger.error(f"GET_POINTS_HISTORY: Invalid input - user_id={user_id}, limit={limit}")
            return []
            
        async with aiosqlite.connect(REFERRAL_DB_PATH) as db:
            async with db.execute('''
                SELECT amount, type, description, created_at
                FROM points_transactions 
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ''', (user_id, limit)) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        'amount': row[0],
                        'type': row[1],
                        'description': row[2],
                        'created_at': row[3]
                    } for row in rows
                ]
                
    except Exception as e:
        logger.error(f"GET_POINTS_HISTORY: Critical error - {e}")
        return []

async def get_referral_stats(user_id: str) -> dict:
    """Получает статистику рефералов"""
    try:
        if not user_id:
            logger.error(f"GET_REFERRAL_STATS: Invalid input - user_id={user_id}")
            return {'total_referrals': 0, 'successful_referrals': 0, 'pending_referrals': 0}
            
        logger.info(f"GET_REFERRAL_STATS: user_id={user_id}")
        
        async with aiosqlite.connect(REFERRAL_DB_PATH) as db:
            # Общее количество рефералов
            async with db.execute('''
                SELECT COUNT(*) FROM referrals WHERE referrer_id = ?
            ''', (user_id,)) as cursor:
                total_referrals = (await cursor.fetchone())[0]
            
            # Успешные рефералы
            async with db.execute('''
                SELECT COUNT(*) FROM referrals 
                WHERE referrer_id = ? AND reward_given = 1
            ''', (user_id,)) as cursor:
                successful_referrals = (await cursor.fetchone())[0]
            
            stats = {
                'total_referrals': total_referrals,
                'successful_referrals': successful_referrals,
                'pending_referrals': total_referrals - successful_referrals
            }
            
            logger.info(f"GET_REFERRAL_STATS: result={stats}")
            return stats
            
    except Exception as e:
        logger.error(f"GET_REFERRAL_STATS: Critical error - {e}")
        return {'total_referrals': 0, 'successful_referrals': 0, 'pending_referrals': 0}

# Удалено: register_bot_user (заменено на register_simple_user)

# Удалено: has_ever_used_bot (заменено на is_known_user)

# Удалено: update_user_purchase_stats (агрегаты по покупкам больше не ведем)

# ===== АТОМАРНЫЕ ОПЕРАЦИИ =====

async def atomic_referral_reward(referrer_id: str, referred_id: str, payment_id: str, server_manager=None) -> bool:
    """Атомарно выдает реферальную награду и отмечает ее как выданную"""
    try:
        if not referrer_id or not referred_id or not payment_id:
            logger.error(f"ATOMIC_REFERRAL_REWARD: Invalid input - referrer_id={referrer_id}, referred_id={referred_id}, payment_id={payment_id}")
            return False
        
        # Проверяем, что реферал действительно новый по таблице users
        if await is_known_user(referred_id):
            logger.info(f"ATOMIC_REFERRAL_REWARD: referred user {referred_id} is known, skipping reward")
            return False
            
        async with aiosqlite.connect(REFERRAL_DB_PATH) as db:
            # Начинаем транзакцию
            await db.execute('BEGIN TRANSACTION')
            
            try:
                # Выдаем балл рефереру
                await db.execute('''
                    INSERT OR REPLACE INTO user_points (user_id, points, total_earned, last_updated)
                    VALUES (?, 
                            COALESCE((SELECT points FROM user_points WHERE user_id = ?), 0) + 1,
                            COALESCE((SELECT total_earned FROM user_points WHERE user_id = ?), 0) + 1,
                            ?)
                ''', (referrer_id, referrer_id, referrer_id, int(datetime.datetime.now().timestamp())))
                
                # Записываем транзакцию
                await db.execute('''
                    INSERT INTO points_transactions (user_id, amount, type, description, source_id, created_at)
                    VALUES (?, 1, 'earned', ?, ?, ?)
                ''', (referrer_id, f"Реферальная награда за {referred_id}", referred_id, int(datetime.datetime.now().timestamp())))
                
                # Отмечаем награду как выданную
                await db.execute('''
                    UPDATE referrals 
                    SET reward_given = 1, payment_id = ?
                    WHERE referrer_id = ? AND referred_id = ?
                ''', (payment_id, referrer_id, referred_id))
                
                # Подтверждаем транзакцию
                await db.commit()
                # Оставляем только последние 5 транзакций для реферера
                await prune_points_history(referrer_id, keep=5)
                logger.info(f"ATOMIC_REFERRAL_REWARD: Successfully awarded reward to {referrer_id} for {referred_id}")
                return True
                
            except Exception as e:
                # Откатываем транзакцию при ошибке
                await db.execute('ROLLBACK')
                logger.error(f"ATOMIC_REFERRAL_REWARD: Transaction failed - {e}")
                return False
                
    except Exception as e:
        logger.error(f"ATOMIC_REFERRAL_REWARD: Critical error - {e}")
        return False

async def atomic_refund_points(user_id: str, points: int, description: str) -> bool:
    """Атомарно возвращает баллы пользователю"""
    try:
        if not user_id or not isinstance(points, int) or points <= 0:
            logger.error(f"ATOMIC_REFUND_POINTS: Invalid input - user_id={user_id}, points={points}")
            return False
            
        async with aiosqlite.connect(REFERRAL_DB_PATH) as db:
            # Начинаем транзакцию
            await db.execute('BEGIN TRANSACTION')
            
            try:
                # Возвращаем баллы
                await db.execute('''
                    INSERT OR REPLACE INTO user_points (user_id, points, total_earned, last_updated)
                    VALUES (?, 
                            COALESCE((SELECT points FROM user_points WHERE user_id = ?), 0) + ?,
                            COALESCE((SELECT total_earned FROM user_points WHERE user_id = ?), 0) + ?,
                            ?)
                ''', (user_id, user_id, points, user_id, points, int(datetime.datetime.now().timestamp())))
                
                # Записываем транзакцию
                await db.execute('''
                    INSERT INTO points_transactions (user_id, amount, type, description, source_id, created_at)
                    VALUES (?, ?, 'refund', ?, ?, ?)
                ''', (user_id, points, description, None, int(datetime.datetime.now().timestamp())))
                
                # Подтверждаем транзакцию
                await db.commit()
                # Оставляем только последние 5 транзакций пользователя
                await prune_points_history(user_id, keep=5)
                logger.info(f"ATOMIC_REFUND_POINTS: Successfully refunded {points} points to user {user_id}")
                return True
                
            except Exception as e:
                # Откатываем транзакцию при ошибке
                await db.execute('ROLLBACK')
                logger.error(f"ATOMIC_REFUND_POINTS: Transaction failed - {e}")
                return False
                
    except Exception as e:
        logger.error(f"ATOMIC_REFUND_POINTS: Critical error - {e}")
        return False

