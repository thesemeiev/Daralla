"""
База данных для системы уведомлений
Содержит таблицы для хранения уведомлений, метрик и кэша
"""

import aiosqlite
import datetime
import logging
import os
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Определяем путь к базе данных относительно корневой папки проекта
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTIFICATIONS_DB_PATH = os.path.join(BASE_DIR, 'notifications.db')

async def init_notifications_db():
    """Инициализация базы данных уведомлений"""
    try:
        async with aiosqlite.connect(NOTIFICATIONS_DB_PATH) as db:
            # Таблица для хранения отправленных уведомлений
            await db.execute("""
                CREATE TABLE IF NOT EXISTS sent_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    key_email TEXT NOT NULL,
                    notification_type TEXT NOT NULL,
                    sent_at INTEGER NOT NULL,
                    server_name TEXT,
                    UNIQUE(user_id, key_email, notification_type)
                )
            """)
            
            # Таблица для метрик уведомлений
            await db.execute("""
                CREATE TABLE IF NOT EXISTS notification_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    total_sent INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    failed_count INTEGER DEFAULT 0,
                    blocked_users INTEGER DEFAULT 0,
                    notification_type TEXT NOT NULL,
                    UNIQUE(date, notification_type)
                )
            """)
            
            # Таблица для отслеживания эффективности
            await db.execute("""
                CREATE TABLE IF NOT EXISTS notification_effectiveness (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    key_email TEXT NOT NULL,
                    notification_type TEXT NOT NULL,
                    sent_at INTEGER NOT NULL,
                    action_taken TEXT,  -- 'extended', 'ignored', 'expired'
                    action_taken_at INTEGER,
                    days_until_expiry INTEGER
                )
            """)
            
            # Таблица для настроек уведомлений
            await db.execute("""
                CREATE TABLE IF NOT EXISTS notification_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                )
            """)
            
            # Создаем индексы для быстрого поиска
            await db.execute("CREATE INDEX IF NOT EXISTS idx_sent_notifications_user ON sent_notifications(user_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_sent_notifications_email ON sent_notifications(key_email)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_sent_notifications_type ON sent_notifications(notification_type)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_sent_notifications_sent_at ON sent_notifications(sent_at)")
            
            await db.execute("CREATE INDEX IF NOT EXISTS idx_metrics_date ON notification_metrics(date)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_metrics_type ON notification_metrics(notification_type)")
            
            await db.execute("CREATE INDEX IF NOT EXISTS idx_effectiveness_user ON notification_effectiveness(user_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_effectiveness_action ON notification_effectiveness(action_taken)")
            
            await db.commit()
            logger.info("База данных уведомлений инициализирована")
            
    except Exception as e:
        logger.error(f"Ошибка инициализации базы данных уведомлений: {e}")
        raise

async def is_notification_sent(user_id: str, key_email: str, notification_type: str) -> bool:
    """Проверяет, было ли уже отправлено уведомление"""
    try:
        async with aiosqlite.connect(NOTIFICATIONS_DB_PATH) as db:
            cursor = await db.execute("""
                SELECT id FROM sent_notifications 
                WHERE user_id = ? AND key_email = ? AND notification_type = ?
            """, (user_id, key_email, notification_type))
            
            result = await cursor.fetchone()
            return result is not None
            
    except Exception as e:
        logger.error(f"Ошибка проверки отправленного уведомления: {e}")
        return False

async def mark_notification_sent(user_id: str, key_email: str, notification_type: str, server_name: str = None) -> bool:
    """Отмечает уведомление как отправленное"""
    try:
        async with aiosqlite.connect(NOTIFICATIONS_DB_PATH) as db:
            now = int(datetime.datetime.now().timestamp())
            
            await db.execute("""
                INSERT OR REPLACE INTO sent_notifications 
                (user_id, key_email, notification_type, sent_at, server_name)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, key_email, notification_type, now, server_name))
            
            await db.commit()
            return True
            
    except Exception as e:
        logger.error(f"Ошибка сохранения отправленного уведомления: {e}")
        return False

async def record_notification_metrics(notification_type: str, success: bool, user_blocked: bool = False) -> bool:
    """Записывает метрики уведомления"""
    try:
        async with aiosqlite.connect(NOTIFICATIONS_DB_PATH) as db:
            today = datetime.datetime.now().strftime('%Y-%m-%d')
            
            # Получаем текущие метрики
            cursor = await db.execute("""
                SELECT total_sent, success_count, failed_count, blocked_users
                FROM notification_metrics 
                WHERE date = ? AND notification_type = ?
            """, (today, notification_type))
            
            result = await cursor.fetchone()
            
            if result:
                total_sent, success_count, failed_count, blocked_users = result
                total_sent += 1
                if success:
                    success_count += 1
                else:
                    failed_count += 1
                if user_blocked:
                    blocked_users += 1
                
                await db.execute("""
                    UPDATE notification_metrics 
                    SET total_sent = ?, success_count = ?, failed_count = ?, blocked_users = ?
                    WHERE date = ? AND notification_type = ?
                """, (total_sent, success_count, failed_count, blocked_users, today, notification_type))
            else:
                # Создаем новую запись
                total_sent = 1
                success_count = 1 if success else 0
                failed_count = 0 if success else 1
                blocked_users = 1 if user_blocked else 0
                
                await db.execute("""
                    INSERT INTO notification_metrics 
                    (date, total_sent, success_count, failed_count, blocked_users, notification_type)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (today, total_sent, success_count, failed_count, blocked_users, notification_type))
            
            await db.commit()
            return True
            
    except Exception as e:
        logger.error(f"Ошибка записи метрик уведомления: {e}")
        return False

async def record_notification_effectiveness(user_id: str, key_email: str, notification_type: str, 
                                         action_taken: str = None, days_until_expiry: int = None) -> bool:
    """Записывает эффективность уведомления"""
    try:
        async with aiosqlite.connect(NOTIFICATIONS_DB_PATH) as db:
            now = int(datetime.datetime.now().timestamp())
            action_taken_at = now if action_taken else None
            
            await db.execute("""
                INSERT INTO notification_effectiveness 
                (user_id, key_email, notification_type, sent_at, action_taken, action_taken_at, days_until_expiry)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, key_email, notification_type, now, action_taken, action_taken_at, days_until_expiry))
            
            await db.commit()
            return True
            
    except Exception as e:
        logger.error(f"Ошибка записи эффективности уведомления: {e}")
        return False

async def cleanup_old_notifications(days_to_keep: int = 30) -> int:
    """Очищает старые записи уведомлений"""
    try:
        async with aiosqlite.connect(NOTIFICATIONS_DB_PATH) as db:
            cutoff_time = int((datetime.datetime.now() - datetime.timedelta(days=days_to_keep)).timestamp())
            
            # Удаляем старые отправленные уведомления
            cursor = await db.execute("""
                DELETE FROM sent_notifications WHERE sent_at < ?
            """, (cutoff_time,))
            deleted_notifications = cursor.rowcount
            
            # Удаляем старые записи эффективности
            cursor = await db.execute("""
                DELETE FROM notification_effectiveness WHERE sent_at < ?
            """, (cutoff_time,))
            deleted_effectiveness = cursor.rowcount
            
            await db.commit()
            
            logger.info(f"Очищено {deleted_notifications} уведомлений и {deleted_effectiveness} записей эффективности")
            return deleted_notifications + deleted_effectiveness
            
    except Exception as e:
        logger.error(f"Ошибка очистки старых уведомлений: {e}")
        return 0

async def get_notification_stats(days: int = 7) -> Dict:
    """Получает статистику уведомлений за указанное количество дней"""
    try:
        async with aiosqlite.connect(NOTIFICATIONS_DB_PATH) as db:
            start_date = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime('%Y-%m-%d')
            
            # Общая статистика
            cursor = await db.execute("""
                SELECT 
                    SUM(total_sent) as total_sent,
                    SUM(success_count) as success_count,
                    SUM(failed_count) as failed_count,
                    SUM(blocked_users) as blocked_users
                FROM notification_metrics 
                WHERE date >= ?
            """, (start_date,))
            
            result = await cursor.fetchone()
            total_sent, success_count, failed_count, blocked_users = result or (0, 0, 0, 0)
            
            # Статистика по типам уведомлений
            cursor = await db.execute("""
                SELECT 
                    notification_type,
                    SUM(total_sent) as total_sent,
                    SUM(success_count) as success_count,
                    SUM(failed_count) as failed_count
                FROM notification_metrics 
                WHERE date >= ?
                GROUP BY notification_type
                ORDER BY total_sent DESC
            """, (start_date,))
            
            type_stats = []
            for row in await cursor.fetchall():
                type_stats.append({
                    'type': row[0],
                    'total_sent': row[1],
                    'success_count': row[2],
                    'failed_count': row[3],
                    'success_rate': (row[2] / row[1] * 100) if row[1] > 0 else 0
                })
            
            # Статистика эффективности
            cursor = await db.execute("""
                SELECT 
                    action_taken,
                    COUNT(*) as count
                FROM notification_effectiveness 
                WHERE sent_at >= ?
                GROUP BY action_taken
            """, (int((datetime.datetime.now() - datetime.timedelta(days=days)).timestamp()),))
            
            effectiveness_stats = {}
            for row in await cursor.fetchall():
                effectiveness_stats[row[0] or 'no_action'] = row[1]
            
            return {
                'total_sent': total_sent,
                'success_count': success_count,
                'failed_count': failed_count,
                'blocked_users': blocked_users,
                'success_rate': (success_count / total_sent * 100) if total_sent > 0 else 0,
                'type_stats': type_stats,
                'effectiveness_stats': effectiveness_stats
            }
            
    except Exception as e:
        logger.error(f"Ошибка получения статистики уведомлений: {e}")
        return {}

async def get_daily_notification_stats() -> List[Dict]:
    """Получает ежедневную статистику уведомлений за последние 30 дней"""
    try:
        async with aiosqlite.connect(NOTIFICATIONS_DB_PATH) as db:
            cursor = await db.execute("""
                SELECT 
                    date,
                    SUM(total_sent) as total_sent,
                    SUM(success_count) as success_count,
                    SUM(failed_count) as failed_count,
                    SUM(blocked_users) as blocked_users
                FROM notification_metrics 
                WHERE date >= date('now', '-30 days')
                GROUP BY date
                ORDER BY date DESC
            """)
            
            stats = []
            for row in await cursor.fetchall():
                stats.append({
                    'date': row[0],
                    'total_sent': row[1],
                    'success_count': row[2],
                    'failed_count': row[3],
                    'blocked_users': row[4],
                    'success_rate': (row[2] / row[1] * 100) if row[1] > 0 else 0
                })
            
            return stats
            
    except Exception as e:
        logger.error(f"Ошибка получения ежедневной статистики: {e}")
        return []

async def clear_user_notifications(user_id: str) -> int:
    """Очищает все уведомления для пользователя (при блокировке бота)"""
    try:
        async with aiosqlite.connect(NOTIFICATIONS_DB_PATH) as db:
            # Удаляем отправленные уведомления
            cursor = await db.execute("""
                DELETE FROM sent_notifications WHERE user_id = ?
            """, (user_id,))
            deleted_notifications = cursor.rowcount
            
            # Удаляем записи эффективности
            cursor = await db.execute("""
                DELETE FROM notification_effectiveness WHERE user_id = ?
            """, (user_id,))
            deleted_effectiveness = cursor.rowcount
            
            await db.commit()
            
            logger.info(f"Очищено {deleted_notifications} уведомлений и {deleted_effectiveness} записей эффективности для пользователя {user_id}")
            return deleted_notifications + deleted_effectiveness
            
    except Exception as e:
        logger.error(f"Ошибка очистки уведомлений пользователя {user_id}: {e}")
        return 0

async def get_notification_settings() -> Dict[str, str]:
    """Получает настройки уведомлений"""
    try:
        async with aiosqlite.connect(NOTIFICATIONS_DB_PATH) as db:
            cursor = await db.execute("SELECT key, value FROM notification_settings")
            settings = {}
            for row in await cursor.fetchall():
                settings[row[0]] = row[1]
            return settings
    except Exception as e:
        logger.error(f"Ошибка получения настроек уведомлений: {e}")
        return {}

async def set_notification_setting(key: str, value: str) -> bool:
    """Устанавливает настройку уведомлений"""
    try:
        async with aiosqlite.connect(NOTIFICATIONS_DB_PATH) as db:
            now = int(datetime.datetime.now().timestamp())
            await db.execute("""
                INSERT OR REPLACE INTO notification_settings (key, value, updated_at)
                VALUES (?, ?, ?)
            """, (key, value, now))
            await db.commit()
            return True
    except Exception as e:
        logger.error(f"Ошибка установки настройки уведомлений {key}: {e}")
        return False
