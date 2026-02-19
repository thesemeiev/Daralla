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

        # Настройки уведомлений (вкл/выкл, время)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS notification_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at INTEGER
            )
        ''')

        # Правила уведомлений (динамическая конфигурация)
        await db.execute('''
            CREATE TABLE IF NOT EXISTS notification_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                trigger_hours INTEGER NOT NULL,
                message_template TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at INTEGER NOT NULL
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
        cursor = await db.execute("DELETE FROM sent_notifications WHERE sent_at < ?", (cutoff,))
        deleted_count = cursor.rowcount
        await db.commit()
        return deleted_count

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
            rows = await cur.fetchall()
            return [dict(row) for row in rows]

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


# ── notification_rules CRUD ──

async def get_all_notification_rules():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM notification_rules ORDER BY event_type, trigger_hours"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_active_notification_rules():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM notification_rules WHERE is_active = 1 ORDER BY event_type, trigger_hours"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def create_notification_rule(event_type: str, trigger_hours: int, message_template: str) -> int:
    now = int(datetime.datetime.now().timestamp())
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('''
            INSERT INTO notification_rules (event_type, trigger_hours, message_template, is_active, created_at)
            VALUES (?, ?, ?, 1, ?)
        ''', (event_type, trigger_hours, message_template, now))
        await db.commit()
        return cursor.lastrowid


async def update_notification_rule(rule_id: int, **fields):
    allowed = {'event_type', 'trigger_hours', 'message_template', 'is_active'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [rule_id]
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            f"UPDATE notification_rules SET {set_clause} WHERE id = ?", values
        )
        await db.commit()
        return cursor.rowcount > 0


async def delete_notification_rule(rule_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM notification_rules WHERE id = ?", (rule_id,))
        await db.commit()
        return cursor.rowcount > 0


async def get_notification_rule_by_id(rule_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM notification_rules WHERE id = ?", (rule_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def seed_default_notification_rules():
    """Fills notification_rules with legacy defaults if the table is empty."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM notification_rules") as cur:
            (count,) = await cur.fetchone()
        if count > 0:
            return

    defaults = [
        (
            'expiry_warning', -72,
            '<b>Напоминание: ваша подписка истекает!</b>\n\n'
            'Осталось: <b>{time_remaining}</b>\n'
            '{expiry_line}\n'
            'Продлите подписку заранее, чтобы не прерывать использование VPN.'
        ),
        (
            'expiry_warning', -24,
            '<b>Ваша подписка истекает!</b>\n\n'
            'Осталось: <b>{time_remaining}</b>\n'
            '{expiry_line}\n'
            'Продлите подписку заранее, чтобы не прерывать использование VPN.'
        ),
        (
            'expiry_warning', -1,
            '<b>СРОЧНО! Ваша подписка истекает!</b>\n\n'
            'Осталось: <b>{time_remaining}</b>\n'
            '{expiry_line}\n'
            'Продлите подписку сейчас, чтобы не потерять доступ к VPN.'
        ),
    ]
    now = int(datetime.datetime.now().timestamp())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            "INSERT INTO notification_rules (event_type, trigger_hours, message_template, is_active, created_at) VALUES (?, ?, ?, 1, ?)",
            [(et, th, tpl, now) for et, th, tpl in defaults],
        )
        await db.commit()
    logger.info("Seeded %d default notification rules", len(defaults))

