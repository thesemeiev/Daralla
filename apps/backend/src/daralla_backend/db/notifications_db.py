"""
Модуль работы с уведомлениями (Единая БД)
"""
import json
import aiosqlite
import logging
import datetime
from . import DB_PATH

logger = logging.getLogger(__name__)


def render_structured_template(raw: str, *, expires_at: int = None) -> str:
    """Render a message_template (JSON structured or legacy format-string) into final HTML."""
    from daralla_backend.utils import calculate_time_remaining

    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict) or 'title' not in obj:
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        replacements = {}
        if expires_at:
            expiry_dt = datetime.datetime.fromtimestamp(expires_at)
            replacements['time_remaining'] = calculate_time_remaining(expires_at)
            replacements['expiry_line'] = f"Истекает: <b>{expiry_dt.strftime('%d.%m.%Y %H:%M')}</b>"
        else:
            replacements['time_remaining'] = ''
            replacements['expiry_line'] = ''
        try:
            return raw.format(**replacements)
        except KeyError:
            return raw

    title = obj.get('title', '')
    body = obj.get('body', '')
    show_time = obj.get('show_time_remaining', False)
    show_expiry = obj.get('show_expiry_date', False)

    parts = []
    if title:
        parts.append(f"<b>{title}</b>")
        parts.append('')

    if show_time or show_expiry:
        if show_time:
            if expires_at:
                parts.append(f"Осталось: <b>{calculate_time_remaining(expires_at)}</b>")
            else:
                parts.append("Осталось: <b>—</b>")
        if show_expiry:
            if expires_at:
                expiry_dt = datetime.datetime.fromtimestamp(expires_at)
                parts.append(f"Истекает: <b>{expiry_dt.strftime('%d.%m.%Y %H:%M')}</b>")
            else:
                parts.append("Истекает: <b>—</b>")
        parts.append('')

    if body:
        parts.append(body)

    return '\n'.join(parts).strip()

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
                created_at INTEGER NOT NULL,
                repeat_every_hours INTEGER DEFAULT 0,
                max_repeats INTEGER DEFAULT 1
            )
        ''')

        # Миграция: добавляем столбцы если их нет (для существующих БД)
        try:
            await db.execute("ALTER TABLE notification_rules ADD COLUMN repeat_every_hours INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE notification_rules ADD COLUMN max_repeats INTEGER DEFAULT 1")
        except Exception:
            pass

        # Индекс для быстрого поиска отправленных уведомлений
        await db.execute('''
            CREATE INDEX IF NOT EXISTS idx_sent_notif_lookup
            ON sent_notifications(user_id, subscription_id, notification_type)
        ''')

        # Миграция: переименовываем nosub_rule_* → rule_* для единообразия
        await db.execute('''
            UPDATE sent_notifications
            SET notification_type = REPLACE(notification_type, 'nosub_rule_', 'rule_')
            WHERE notification_type LIKE 'nosub_rule_%'
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

async def cleanup_old_notifications(days: int = 30, *, dry_run: bool = False):
    cutoff = int((datetime.datetime.now() - datetime.timedelta(days=days)).timestamp())
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM sent_notifications WHERE sent_at < ?",
            (cutoff,),
        ) as cur:
            row = await cur.fetchone()
            candidate_count = row[0] if row else 0
        if candidate_count <= 0:
            return 0
        if dry_run:
            logger.info(
                "NOTIFICATIONS_CLEANUP_DRY_RUN: would delete %s rows older than %s days",
                candidate_count,
                days,
            )
            return candidate_count
        cursor = await db.execute(
            "DELETE FROM sent_notifications WHERE sent_at < ?",
            (cutoff,),
        )
        deleted_count = cursor.rowcount
        await db.commit()
        return deleted_count


async def cleanup_old_notification_metrics(days: int = 730, *, dry_run: bool = False) -> int:
    cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM notification_metrics WHERE date < ?",
            (cutoff_date,),
        ) as cur:
            row = await cur.fetchone()
            candidate_count = row[0] if row else 0
        if candidate_count <= 0:
            return 0
        if dry_run:
            logger.info(
                "NOTIFICATION_METRICS_CLEANUP_DRY_RUN: would delete %s rows before %s",
                candidate_count,
                cutoff_date,
            )
            return candidate_count
        cursor = await db.execute(
            "DELETE FROM notification_metrics WHERE date < ?",
            (cutoff_date,),
        )
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


async def reset_no_sub_notifications(user_id: str):
    """Сбрасывает счётчик no_subscription уведомлений при покупке подписки,
    чтобы цикл повторов начался заново если пользователь снова уйдёт."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM sent_notifications WHERE user_id = ? AND subscription_id = 0 AND notification_type LIKE 'rule_%'",
            (user_id,),
        )
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


async def create_notification_rule(event_type: str, trigger_hours: int, message_template: str,
                                   repeat_every_hours: int = 0, max_repeats: int = 1) -> int:
    now = int(datetime.datetime.now().timestamp())
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('''
            INSERT INTO notification_rules
                (event_type, trigger_hours, message_template, is_active, created_at, repeat_every_hours, max_repeats)
            VALUES (?, ?, ?, 1, ?, ?, ?)
        ''', (event_type, trigger_hours, message_template, now, repeat_every_hours, max_repeats))
        await db.commit()
        return cursor.lastrowid


async def update_notification_rule(rule_id: int, **fields):
    allowed = {'event_type', 'trigger_hours', 'message_template', 'is_active', 'repeat_every_hours', 'max_repeats'}
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


async def get_notification_send_count(user_id: str, subscription_id: int, notification_type: str) -> int:
    """Сколько раз данное уведомление было отправлено пользователю"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM sent_notifications WHERE user_id = ? AND subscription_id = ? AND notification_type = ?",
            (user_id, subscription_id, notification_type)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0


async def get_last_notification_send_time(user_id: str, subscription_id: int, notification_type: str) -> int | None:
    """Timestamp последней отправки уведомления пользователю"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT MAX(sent_at) FROM sent_notifications WHERE user_id = ? AND subscription_id = ? AND notification_type = ?",
            (user_id, subscription_id, notification_type)
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None



