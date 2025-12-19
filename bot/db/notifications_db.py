"""
Модуль работы с уведомлениями (Единая БД)
"""
import aiosqlite
import logging
import datetime
from . import DB_PATH

logger = logging.getLogger(__name__)

async def init_notifications_db():
    """Инициализирует таблицы уведомлений в единой БД"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Таблица отправленных уведомлений (для предотвращения спама)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS sent_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                subscription_id INTEGER NOT NULL,
                notification_type TEXT NOT NULL, -- e.g., 'expiry_3d', 'expiry_1d', 'expired'
                sent_at INTEGER NOT NULL,
                server_name TEXT -- Опционально, если уведомление по конкретному серверу
            )
        ''')

        # Таблица метрик уведомлений (для админки)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS notification_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL, -- YYYY-MM-DD
                total_sent INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                blocked_users INTEGER DEFAULT 0,
                notification_type TEXT NOT NULL
            )
        ''')

        # Таблица эффективности (нажал ли пользователь на кнопку после уведомления)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS notification_effectiveness (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                subscription_id INTEGER NOT NULL,
                notification_type TEXT NOT NULL,
                sent_at INTEGER NOT NULL,
                action_taken TEXT, -- 'clicked_extend', 'renewed'
                action_taken_at INTEGER,
                days_until_expiry INTEGER
            )
        ''')

        # Настройки уведомлений (вкл/выкл, время)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS notification_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at INTEGER
            )
        ''')
        await db.commit()

async def record_notification_metrics(notification_type: str, success: bool = True, is_blocked: bool = False):
    date_str = datetime.datetime.now().strftime('%Y-%m-%d')
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO notification_metrics (date, total_sent, success_count, failed_count, blocked_users, notification_type)
            VALUES (?, 1, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                total_sent = total_sent + 1,
                success_count = success_count + (?),
                failed_count = failed_count + (?),
                blocked_users = blocked_users + (?)
        ''', (date_str, 1 if success else 0, 0 if success else 1, 1 if is_blocked else 0, notification_type,
              1 if success else 0, 0 if success else 1, 1 if is_blocked else 0))
        await db.commit()

async def cleanup_old_notifications(days: int = 30):
    cutoff = int((datetime.datetime.now() - datetime.timedelta(days=days)).timestamp())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM sent_notifications WHERE sent_at < ?", (cutoff,))
        await db.execute("DELETE FROM notification_effectiveness WHERE sent_at < ?", (cutoff,))
        await db.commit()

async def get_notification_stats(days: int = 7):
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime('%Y-%m-%d')
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # Общая статистика
        async with db.execute('''
            SELECT SUM(total_sent) as total_sent, 
                   SUM(success_count) as success_count, 
                   SUM(failed_count) as failed_count, 
                   SUM(blocked_users) as blocked_users
            FROM notification_metrics 
            WHERE date >= ?
        ''', (cutoff,)) as cur:
            row = await cur.fetchone()
            stats = dict(row) if row and row['total_sent'] else {
                'total_sent': 0, 'success_count': 0, 'failed_count': 0, 'blocked_users': 0
            }

        # Расчет success_rate
        if stats['total_sent'] > 0:
            stats['success_rate'] = (stats['success_count'] / stats['total_sent']) * 100
        else:
            stats['success_rate'] = 0

        # Статистика по типам
        async with db.execute('''
            SELECT notification_type, SUM(total_sent) as total, SUM(success_count) as success
            FROM notification_metrics 
            WHERE date >= ?
            GROUP BY notification_type
        ''', (cutoff,)) as cur:
            rows = await cur.fetchall()
            stats['by_type'] = [dict(r) for r in rows]

        # Статистика эффективности
        async with db.execute('''
            SELECT action_taken, COUNT(*) as count
            FROM notification_effectiveness
            WHERE sent_at >= ?
            GROUP BY action_taken
        ''', (int((datetime.datetime.now() - datetime.timedelta(days=days)).timestamp()),)) as cur:
            rows = await cur.fetchall()
            stats['effectiveness_stats'] = {r['action_taken']: r['count'] for r in rows}

        return stats

async def get_daily_notification_stats(days: int = 14):
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime('%Y-%m-%d')
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT date, SUM(total_sent) as total, SUM(success_count) as success
            FROM notification_metrics 
            WHERE date >= ?
            GROUP BY date
            ORDER BY date DESC
        ''', (cutoff,)) as cur:
            return [dict(row) for row in cur]

async def clear_user_notifications(user_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM sent_notifications WHERE user_id = ?", (user_id,))
        await db.commit()

async def get_notification_settings():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT key, value FROM notification_settings") as cur:
            rows = await cur.fetchall()
            return {row[0]: row[1] for row in rows}

async def set_notification_setting(key: str, value: str):
    now = int(datetime.datetime.now().timestamp())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT OR REPLACE INTO notification_settings (key, value, updated_at)
            VALUES (?, ?, ?)
        ''', (key, value, now))
        await db.commit()

async def is_subscription_notification_sent(user_id: str, subscription_id: int, notification_type: str) -> bool:
    """Проверяет, было ли уже отправлено такое уведомление для конкретной подписки за последние 24 часа"""
    yesterday = int((datetime.datetime.now() - datetime.timedelta(hours=24)).timestamp())
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('''
            SELECT 1 FROM sent_notifications 
            WHERE user_id = ? AND subscription_id = ? AND notification_type = ? AND sent_at > ?
            LIMIT 1
        ''', (user_id, subscription_id, notification_type, yesterday)) as cur:
            return (await cur.fetchone()) is not None

async def mark_subscription_notification_sent(user_id: str, subscription_id: int, notification_type: str, server_name: str = None):
    now = int(datetime.datetime.now().timestamp())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO sent_notifications (user_id, subscription_id, notification_type, sent_at, server_name)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, subscription_id, notification_type, now, server_name))
        await db.commit()

async def clear_subscription_notifications(subscription_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM sent_notifications WHERE subscription_id = ?", (subscription_id,))
        await db.commit()

async def record_subscription_notification_effectiveness(user_id: str, subscription_id: int, notification_type: str, action: str):
    now = int(datetime.datetime.now().timestamp())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            UPDATE notification_effectiveness 
            SET action_taken = ?, action_taken_at = ?
            WHERE user_id = ? AND subscription_id = ? AND notification_type = ? AND action_taken IS NULL
        ''', (action, now, user_id, subscription_id, notification_type))
        await db.commit()
