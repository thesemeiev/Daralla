"""
Модуль работы с подписками.
Таблицы: subscriptions, subscription_servers.
"""
import aiosqlite
import datetime
import json
import logging
import time
import uuid
from collections import defaultdict
from . import DB_PATH

logger = logging.getLogger(__name__)


async def init_subscriptions_db():
    """Инициализирует таблицы subscriptions, subscription_servers."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscriber_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                period TEXT NOT NULL,
                device_limit INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                subscription_token TEXT UNIQUE NOT NULL,
                price REAL NOT NULL,
                name TEXT,
                group_id INTEGER,
                sync_revision INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (subscriber_id) REFERENCES users(id),
                FOREIGN KEY (group_id) REFERENCES server_groups(id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS subscription_servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscription_id INTEGER NOT NULL,
                server_name TEXT NOT NULL,
                client_email TEXT NOT NULL,
                client_id TEXT,
                UNIQUE(subscription_id, server_name),
                FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
            )
        """)
        await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_subscription_servers_unique ON subscription_servers(subscription_id, server_name)")

        await db.commit()


async def create_subscription(subscriber_id: int, period: str, device_limit: int, price: float, expires_at: int, name: str = None, group_id: int = None):
    """Создаёт новую подписку. Если group_id не передан — выбирается через resolve_group_id
    (балансировка → дефолтная группа)."""
    from .servers_db import resolve_group_id
    token = uuid.uuid4().hex[:24]
    now = int(datetime.datetime.now().timestamp())
    group_id = await resolve_group_id(group_id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """INSERT INTO subscriptions 
               (subscriber_id, status, period, device_limit, created_at, expires_at, subscription_token, price, name, group_id, sync_revision)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (subscriber_id, 'active', period, device_limit, now, expires_at, token, price, name, group_id, 1)
        ) as cur:
            sub_id = cur.lastrowid
            await db.commit()

        # Сбрасываем счётчик no_subscription уведомлений для этого пользователя
        async with db.execute("SELECT user_id FROM users WHERE id = ?", (subscriber_id,)) as cur:
            user_row = await cur.fetchone()
        if user_row:
            from .notifications_db import reset_no_sub_notifications
            await reset_no_sub_notifications(user_row[0])

        return sub_id, token


async def get_all_active_subscriptions():
    """Возвращает все активные подписки (с учетом expires_at и исключая deleted)"""
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
    Включает: active и expired, исключает deleted.
    """
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
        if status == "deleted":
            now = int(time.time())
            await db.execute(
                "UPDATE subscriptions "
                "SET status = ?, deleted_at = COALESCE(deleted_at, ?), sync_revision = COALESCE(sync_revision, 0) + 1 "
                "WHERE id = ?",
                (status, now, subscription_id),
            )
        else:
            await db.execute(
                "UPDATE subscriptions "
                "SET status = ?, deleted_at = NULL, sync_revision = COALESCE(sync_revision, 0) + 1 "
                "WHERE id = ?",
                (status, subscription_id),
            )
        await db.commit()


async def update_subscription_name(subscription_id: int, name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE subscriptions "
            "SET name = ?, sync_revision = COALESCE(sync_revision, 0) + 1 "
            "WHERE id = ?",
            (name, subscription_id),
        )
        await db.commit()


async def update_subscription_expiry(subscription_id: int, new_expires_at: int):
    """Обновляет expires_at и автоматически обновляет статус на основе expires_at"""
    current_time = int(time.time())

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT status FROM subscriptions WHERE id = ?", (subscription_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                logger.warning(f"Подписка {subscription_id} не найдена при обновлении expires_at")
                return
            current_status = row[0]

        await db.execute(
            "UPDATE subscriptions "
            "SET expires_at = ?, sync_revision = COALESCE(sync_revision, 0) + 1 "
            "WHERE id = ?",
            (new_expires_at, subscription_id),
        )

        if current_status != 'deleted':
            if new_expires_at > current_time:
                if current_status == 'expired':
                    await db.execute(
                        "UPDATE subscriptions "
                        "SET status = 'active', sync_revision = COALESCE(sync_revision, 0) + 1 "
                        "WHERE id = ?",
                        (subscription_id,),
                    )
                    logger.info(f"Подписка {subscription_id} автоматически активирована (продлена до {new_expires_at})")
            else:
                if current_status == 'active':
                    await db.execute(
                        "UPDATE subscriptions "
                        "SET status = 'expired', sync_revision = COALESCE(sync_revision, 0) + 1 "
                        "WHERE id = ?",
                        (subscription_id,),
                    )
                    logger.info(f"Подписка {subscription_id} автоматически истекла (expires_at: {new_expires_at})")

        await db.commit()


async def update_subscription_device_limit(subscription_id: int, new_device_limit: int):
    """Обновляет лимит устройств/IP для подписки"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE subscriptions "
            "SET device_limit = ?, sync_revision = COALESCE(sync_revision, 0) + 1 "
            "WHERE id = ?",
            (new_device_limit, subscription_id),
        )
        await db.commit()


async def update_subscription_price(subscription_id: int, price: float):
    """Обновляет цену подписки"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE subscriptions "
            "SET price = ?, sync_revision = COALESCE(sync_revision, 0) + 1 "
            "WHERE id = ?",
            (price, subscription_id),
        )
        await db.commit()


async def get_subscription_sync_revision(subscription_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COALESCE(sync_revision, 0) FROM subscriptions WHERE id = ?",
            (subscription_id,),
        ) as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else 0


def is_subscription_active(sub: dict) -> bool:
    """Проверяет, активна ли подписка (status='active' и expires_at > current_time). deleted всегда неактивна."""
    current_time = int(time.time())
    if sub.get('status') == 'deleted':
        return False
    return sub.get('status') == 'active' and sub.get('expires_at', 0) > current_time


async def sync_subscription_statuses():
    """Периодически проверяет и обновляет статусы подписок на основе expires_at. Returns {'expired_count', 'activated_count'}."""
    current_time = int(time.time())

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            UPDATE subscriptions 
            SET status = 'expired',
                sync_revision = COALESCE(sync_revision, 0) + 1
            WHERE status = 'active' 
            AND expires_at < ? 
            AND status != 'deleted'
        """, (current_time,)) as cur:
            expired_count = cur.rowcount

        async with db.execute("""
            UPDATE subscriptions 
            SET status = 'active',
                sync_revision = COALESCE(sync_revision, 0) + 1
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


async def list_subscription_ids_for_group(group_id: int) -> list[int]:
    """ID подписок с данной группой серверов (не удалённые)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM subscriptions WHERE group_id = ? AND status != 'deleted' ORDER BY id",
            (int(group_id),),
        ) as cur:
            rows = await cur.fetchall()
            return [int(r[0]) for r in rows]


async def get_subscription_servers(subscription_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT ss.* FROM subscription_servers ss
            LEFT JOIN servers_config sc ON lower(sc.name) = lower(ss.server_name)
            WHERE ss.subscription_id = ?
            ORDER BY (CASE WHEN sc.id IS NULL THEN 1 ELSE 0 END),
                     COALESCE(sc.client_sort_order, 999999),
                     ss.server_name
            """,
            (subscription_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]


async def get_subscription_servers_for_subscription_ids(subscription_ids: list) -> dict:
    """Все строки subscription_servers для набора подписок одним запросом: sub_id -> [rows]."""
    if not subscription_ids:
        return {}
    unique = list(dict.fromkeys(int(x) for x in subscription_ids))
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        placeholders = ",".join("?" * len(unique))
        q = f"""
            SELECT ss.* FROM subscription_servers ss
            LEFT JOIN servers_config sc ON lower(sc.name) = lower(ss.server_name)
            WHERE ss.subscription_id IN ({placeholders})
            ORDER BY ss.subscription_id,
                     (CASE WHEN sc.id IS NULL THEN 1 ELSE 0 END),
                     COALESCE(sc.client_sort_order, 999999),
                     ss.server_name
        """
        async with db.execute(q, unique) as cur:
            rows = await cur.fetchall()
    by_id = {sid: [] for sid in unique}
    for row in rows:
        d = dict(row)
        sid = d["subscription_id"]
        if sid in by_id:
            by_id[sid].append(d)
    return by_id


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


def _utc_day(ts: int | None = None) -> str:
    return datetime.datetime.utcfromtimestamp(int(ts or time.time())).strftime("%Y-%m-%d")


async def ensure_default_unlimited_bucket(subscription_id: int, name: str = "unlimited") -> int:
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT id FROM subscription_traffic_buckets
            WHERE subscription_id = ? AND name = ?
            LIMIT 1
            """,
            (int(subscription_id), str(name)),
        ) as cur:
            row = await cur.fetchone()
            if row:
                return int(row[0])
        async with db.execute(
            """
            INSERT INTO subscription_traffic_buckets
            (subscription_id, name, limit_bytes, is_unlimited, is_enabled, window_days,
             credit_periods_total, credit_periods_remaining, period_started_at, period_ends_at, created_at, updated_at)
            VALUES (?, ?, 0, 1, 1, 30, 1, 1, ?, ?, ?, ?)
            """,
            (int(subscription_id), str(name), now, now + 30 * 86400, now, now),
        ) as cur:
            bucket_id = int(cur.lastrowid)
        await db.commit()
        return bucket_id


async def create_subscription_traffic_bucket(
    subscription_id: int,
    name: str,
    limit_bytes: int = 0,
    *,
    is_unlimited: bool = False,
    is_enabled: bool = True,
    window_days: int = 30,
    credit_periods_total: int = 1,
    period_started_at: int | None = None,
) -> int:
    now = int(time.time())
    started = int(period_started_at or now)
    ends = started + max(1, int(window_days)) * 86400
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            INSERT INTO subscription_traffic_buckets
            (subscription_id, name, limit_bytes, is_unlimited, is_enabled, window_days,
             credit_periods_total, credit_periods_remaining, period_started_at, period_ends_at, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(subscription_id),
                str(name),
                max(0, int(limit_bytes)),
                1 if is_unlimited else 0,
                1 if is_enabled else 0,
                max(1, int(window_days)),
                max(1, int(credit_periods_total)),
                max(1, int(credit_periods_total)),
                started,
                ends,
                now,
                now,
            ),
        ) as cur:
            bucket_id = int(cur.lastrowid)
        await db.commit()
        return bucket_id


async def update_subscription_traffic_bucket(bucket_id: int, updates: dict) -> bool:
    if not updates:
        return False
    allowed = {
        "name",
        "limit_bytes",
        "is_unlimited",
        "is_enabled",
        "window_days",
        "credit_periods_total",
        "credit_periods_remaining",
        "period_started_at",
        "period_ends_at",
    }
    parts: list[str] = []
    vals: list[object] = []
    for key, value in updates.items():
        if key not in allowed:
            continue
        if key == "limit_bytes":
            value = max(0, int(value))
        if key == "window_days":
            value = max(1, int(value))
        if key == "credit_periods_total":
            value = max(1, int(value))
        if key == "credit_periods_remaining":
            value = max(0, int(value))
        if key in ("is_unlimited", "is_enabled"):
            value = 1 if bool(value) else 0
        parts.append(f"{key} = ?")
        vals.append(value)
    if not parts:
        return False
    parts.append("updated_at = ?")
    vals.append(int(time.time()))
    vals.append(int(bucket_id))
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE subscription_traffic_buckets SET {', '.join(parts)} WHERE id = ?",
            tuple(vals),
        )
        await db.commit()
        return True


async def list_subscription_traffic_buckets(subscription_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM subscription_traffic_buckets
            WHERE subscription_id = ?
            ORDER BY is_unlimited DESC, id ASC
            """,
            (int(subscription_id),),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_subscription_traffic_bucket(bucket_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM subscription_traffic_buckets WHERE id = ? LIMIT 1",
            (int(bucket_id),),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def set_subscription_server_bucket(subscription_id: int, server_name: str, bucket_id: int) -> None:
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO subscription_server_traffic_bucket_map (subscription_id, server_name, bucket_id, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(subscription_id, server_name) DO UPDATE SET
                bucket_id = excluded.bucket_id,
                updated_at = excluded.updated_at
            """,
            (int(subscription_id), str(server_name), int(bucket_id), now),
        )
        await db.commit()


async def set_subscription_servers_bucket(subscription_id: int, server_names: list[str], bucket_id: int) -> int:
    changed = 0
    for server_name in server_names:
        await set_subscription_server_bucket(subscription_id, server_name, bucket_id)
        changed += 1
    return changed


async def get_subscription_server_bucket_map(subscription_id: int) -> dict[str, int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT server_name, bucket_id
            FROM subscription_server_traffic_bucket_map
            WHERE subscription_id = ?
            """,
            (int(subscription_id),),
        ) as cur:
            rows = await cur.fetchall()
            return {str(r[0]): int(r[1]) for r in rows}


async def get_buckets_for_subscription_servers(subscription_id: int) -> dict[str, dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT m.server_name, b.*
            FROM subscription_server_traffic_bucket_map m
            JOIN subscription_traffic_buckets b ON b.id = m.bucket_id
            WHERE m.subscription_id = ?
            """,
            (int(subscription_id),),
        ) as cur:
            rows = await cur.fetchall()
            out: dict[str, dict] = {}
            for row in rows:
                d = dict(row)
                server_name = str(d.pop("server_name"))
                out[server_name] = d
            return out


async def add_bucket_usage_delta(bucket_id: int, bytes_delta: int, *, day_utc: str | None = None) -> None:
    day = day_utc or _utc_day()
    now = int(time.time())
    delta = int(bytes_delta)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO subscription_traffic_usage_daily (bucket_id, day_utc, bytes_used, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(bucket_id, day_utc) DO UPDATE SET
                bytes_used = bytes_used + excluded.bytes_used,
                updated_at = excluded.updated_at
            """,
            (int(bucket_id), str(day), delta, now),
        )
        await db.commit()


async def apply_bucket_usage_adjustment(bucket_id: int, bytes_delta: int, reason: str = "") -> None:
    day = _utc_day()
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO subscription_traffic_adjustments (bucket_id, day_utc, bytes_delta, reason, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (int(bucket_id), day, int(bytes_delta), str(reason or "")[:500], now),
        )
        await db.execute(
            """
            INSERT INTO subscription_traffic_usage_daily (bucket_id, day_utc, bytes_used, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(bucket_id, day_utc) DO UPDATE SET
                bytes_used = bytes_used + excluded.bytes_used,
                updated_at = excluded.updated_at
            """,
            (int(bucket_id), day, int(bytes_delta), now),
        )
        await db.commit()


async def get_bucket_used_bytes_for_window(bucket_id: int, window_days: int = 30) -> int:
    start = (datetime.datetime.utcnow() - datetime.timedelta(days=max(1, int(window_days)) - 1)).strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT COALESCE(SUM(bytes_used), 0)
            FROM subscription_traffic_usage_daily
            WHERE bucket_id = ? AND day_utc >= ?
            """,
            (int(bucket_id), start),
        ) as cur:
            row = await cur.fetchone()
            return int((row[0] if row else 0) or 0)


async def upsert_bucket_enforcement_state(bucket_id: int, is_exhausted: bool) -> None:
    now = int(time.time())
    exhausted_int = 1 if is_exhausted else 0
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO subscription_traffic_enforcement_state
            (bucket_id, is_exhausted, last_checked_at, updated_at, version)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(bucket_id) DO UPDATE SET
                is_exhausted = excluded.is_exhausted,
                last_checked_at = excluded.last_checked_at,
                updated_at = excluded.updated_at,
                version = subscription_traffic_enforcement_state.version + 1
            """,
            (int(bucket_id), exhausted_int, now, now),
        )
        await db.commit()


async def mark_bucket_enforced(bucket_id: int) -> None:
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE subscription_traffic_enforcement_state
            SET last_enforced_at = ?, updated_at = ?
            WHERE bucket_id = ?
            """,
            (now, now, int(bucket_id)),
        )
        await db.commit()


async def get_subscription_bucket_states(subscription_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT b.*,
                   COALESCE(s.is_exhausted, 0) AS is_exhausted,
                   s.last_checked_at,
                   s.last_enforced_at,
                   COALESCE(s.version, 0) AS state_version
            FROM subscription_traffic_buckets b
            LEFT JOIN subscription_traffic_enforcement_state s ON s.bucket_id = b.id
            WHERE b.subscription_id = ?
            ORDER BY b.is_unlimited DESC, b.id ASC
            """,
            (int(subscription_id),),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_bucket_usage_map_for_subscription(subscription_id: int) -> dict[int, int]:
    buckets = await list_subscription_traffic_buckets(subscription_id)
    out: dict[int, int] = {}
    for bucket in buckets:
        out[int(bucket["id"])] = await get_bucket_used_bytes_for_window(
            int(bucket["id"]),
            int(bucket.get("window_days") or 30),
        )
    return out


async def get_subscription_traffic_snapshot(
    subscription_id: int,
    server_name: str,
    client_email: str,
) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM subscription_server_traffic_snapshots
            WHERE subscription_id = ? AND server_name = ? AND client_email = ?
            LIMIT 1
            """,
            (int(subscription_id), str(server_name), str(client_email)),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def upsert_subscription_traffic_snapshot(
    subscription_id: int,
    server_name: str,
    client_email: str,
    *,
    up: int,
    down: int,
) -> None:
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO subscription_server_traffic_snapshots
            (subscription_id, server_name, client_email, last_up, last_down, captured_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(subscription_id, server_name, client_email) DO UPDATE SET
                last_up = excluded.last_up,
                last_down = excluded.last_down,
                captured_at = excluded.captured_at
            """,
            (
                int(subscription_id),
                str(server_name),
                str(client_email),
                max(0, int(up)),
                max(0, int(down)),
                now,
            ),
        )
        await db.commit()


async def delete_bucket_server_assignments(subscription_id: int, bucket_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            DELETE FROM subscription_server_traffic_bucket_map
            WHERE subscription_id = ? AND bucket_id = ?
            """,
            (int(subscription_id), int(bucket_id)),
        )
        await db.commit()
        return int(cur.rowcount or 0)


async def delete_subscription_traffic_bucket(subscription_id: int, bucket_id: int) -> tuple[bool, str | None]:
    """Удаляет лимитированный пакет; ноды с этим пакетом переносятся на безлимитный по умолчанию.

    Возвращает (True, None) или (False, код): not_found | protected_unlimited | last_bucket
    """
    bid = int(bucket_id)
    sid = int(subscription_id)
    bucket = await get_subscription_traffic_bucket(bid)
    if not bucket or int(bucket.get("subscription_id") or 0) != sid:
        return False, "not_found"
    if int(bucket.get("is_unlimited") or 0) == 1:
        return False, "protected_unlimited"
    all_b = await list_subscription_traffic_buckets(sid)
    if len(all_b) <= 1:
        return False, "last_bucket"
    mapping = await get_subscription_server_bucket_map(sid)
    servers_for_bucket = [name for name, b_id in mapping.items() if int(b_id) == bid]
    default_id = await ensure_default_unlimited_bucket(sid)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM subscription_traffic_adjustments WHERE bucket_id = ?", (bid,))
        await db.execute("DELETE FROM subscription_traffic_usage_daily WHERE bucket_id = ?", (bid,))
        await db.execute("DELETE FROM subscription_traffic_enforcement_state WHERE bucket_id = ?", (bid,))
        await db.execute(
            "DELETE FROM subscription_server_traffic_bucket_map WHERE subscription_id = ? AND bucket_id = ?",
            (sid, bid),
        )
        cur = await db.execute(
            "DELETE FROM subscription_traffic_buckets WHERE id = ? AND subscription_id = ?",
            (bid, sid),
        )
        await db.commit()
        if int(cur.rowcount or 0) < 1:
            return False, "not_found"
    for server_name in servers_for_bucket:
        await set_subscription_server_bucket(sid, server_name, default_id)
    return True, None


async def get_subscription_statistics():
    """Возвращает статистику по подпискам и пользователям"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        now = int(datetime.datetime.now().timestamp())

        async with db.execute("SELECT COUNT(*) as count FROM users") as cur:
            row = await cur.fetchone()
            total_users = row['count'] if row else 0

        async with db.execute(
            "SELECT COUNT(*) as count FROM subscriptions WHERE status = 'active' AND expires_at > ?", (now,)
        ) as cur:
            row = await cur.fetchone()
            active_subscriptions = row['count'] if row else 0

        async with db.execute("SELECT COUNT(*) as count FROM subscriptions") as cur:
            row = await cur.fetchone()
            total_subscriptions = row['count'] if row else 0

        async with db.execute("SELECT COUNT(*) as count FROM subscriptions WHERE status = 'expired'") as cur:
            row = await cur.fetchone()
            expired_subscriptions = row['count'] if row else 0

        async with db.execute("SELECT COUNT(*) as count FROM subscriptions WHERE status = 'deleted'") as cur:
            row = await cur.fetchone()
            deleted_subscriptions = row['count'] if row else 0

        async with db.execute("SELECT COUNT(*) as count FROM subscriptions WHERE status = 'trial'") as cur:
            row = await cur.fetchone()
            trial_subscriptions = row['count'] if row else 0

        async with db.execute("""
            SELECT COUNT(DISTINCT u.id) as count 
            FROM users u 
            JOIN subscriptions s ON u.id = s.subscriber_id 
            WHERE s.status = 'active' AND s.expires_at > ?
        """, (now,)) as cur:
            row = await cur.fetchone()
            users_with_active_subs = row['count'] if row else 0

        async with db.execute("""
            SELECT COUNT(*) as count 
            FROM subscription_servers ss
            JOIN subscriptions s ON ss.subscription_id = s.id
            WHERE s.status != 'deleted'
        """) as cur:
            row = await cur.fetchone()
            total_server_clients = row['count'] if row else 0

        async with db.execute("""
            SELECT COUNT(*) as count 
            FROM subscription_servers ss
            JOIN subscriptions s ON ss.subscription_id = s.id
            WHERE s.status = 'active' AND s.expires_at > ?
        """, (now,)) as cur:
            row = await cur.fetchone()
            active_server_clients = row['count'] if row else 0

        async with db.execute("""
            SELECT period, price, COUNT(*) as count
            FROM subscriptions
            WHERE status = 'active' AND expires_at > ? AND price > 0
            GROUP BY period, price
        """, (now,)) as cur:
            rows = await cur.fetchall()

        mrr = 0.0
        for row in rows:
            period = row['period']
            price = row['price']
            count = row['count']
            if period == 'month':
                monthly_price = price
            elif period == '3month':
                monthly_price = price / 3.0
            else:
                monthly_price = price
            mrr += monthly_price * count

        month_ago_timestamp = now - (30 * 24 * 60 * 60)
        async with db.execute("""
            SELECT period, price, COUNT(*) as count
            FROM subscriptions
            WHERE price > 0 AND status != 'deleted'
            AND created_at <= ? AND expires_at >= ?
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
            'total': total_subscriptions,
            'active': active_subscriptions,
            'expired': expired_subscriptions,
            'deleted': deleted_subscriptions,
            'trial': trial_subscriptions,
            'total_subscriptions': total_subscriptions,
            'active_subscriptions': active_subscriptions,
            'expired_subscriptions': expired_subscriptions,
            'deleted_subscriptions': deleted_subscriptions,
            'trial_subscriptions': trial_subscriptions,
            'total_server_clients': total_server_clients,
            'active_server_clients': active_server_clients,
            'mrr': round(mrr, 2),
            'mrr_change': round(mrr_change, 2),
            'mrr_change_percent': round(mrr_change_percent, 2)
        }


async def get_conversion_data(days: int = 30):
    """Возвращает данные конверсии по дням: new_users, purchased, conversion %."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        now = int(datetime.datetime.now().timestamp())
        start_timestamp = now - (days * 24 * 60 * 60)

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

        daily_data = []
        for row in rows:
            date = row['date']
            new_users_count = row['count']
            user_ids_str = row['user_ids']

            if not user_ids_str:
                continue

            user_ids = [int(uid.strip()) for uid in user_ids_str.split(',') if uid.strip()]

            if not user_ids:
                daily_data.append({
                    'date': date,
                    'new_users': new_users_count,
                    'purchased': 0,
                    'conversion': 0.0
                })
                continue

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

            conversion = (purchased_count / new_users_count * 100) if new_users_count > 0 else 0.0

            daily_data.append({
                'date': date,
                'new_users': new_users_count,
                'purchased': purchased_count,
                'conversion': round(conversion, 2)
            })

        return daily_data


async def get_all_subscriptions_by_user(user_id: str, include_deleted: bool = False):
    """Возвращает подписки пользователя. При include_deleted=False исключает status='deleted'."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = (
            """SELECT s.* 
               FROM subscriptions s 
               JOIN users u ON s.subscriber_id = u.id 
               WHERE u.user_id = ?"""
        )
        if not include_deleted:
            query += " AND s.status != 'deleted'"
        query += " ORDER BY s.created_at DESC"
        async with db.execute(query, (user_id,)) as cur:
            rows = await cur.fetchall()
            return [dict(row) for row in rows]


async def get_subscriptions_page(
    page: int = 1,
    limit: int = 20,
    status: str | None = None,
    owner_query: str | None = None,
    long_only: bool = False,
    long_days: int = 180,
):
    """
    Возвращает страницу подписок для админки с возможностью фильтрации.

    - status: фильтр по статусу подписки (active/expired/deleted/trial и т.п.)
    - owner_query: подстрочный поиск по user_id или username владельца
    - long_only: если True, оставляет только "долгие" подписки (длительность >= long_days)
    """
    if page < 1:
        page = 1
    if limit <= 0:
        limit = 20
    offset = (page - 1) * limit

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        base_where = ["1=1"]
        params: list[object] = []

        if status:
            base_where.append("s.status = ?")
            params.append(status)

        if owner_query:
            q = f"%{owner_query.strip()}%"
            base_where.append("(u.user_id LIKE ? OR (u.username IS NOT NULL AND u.username LIKE ?))")
            params.extend([q, q])

        if long_only:
            # Разница в секундах между датой истечения и создания
            min_duration_seconds = long_days * 24 * 60 * 60
            base_where.append("(s.expires_at - s.created_at) >= ?")
            params.append(min_duration_seconds)

        where_sql = " AND ".join(base_where)

        count_query = f"""
            SELECT COUNT(*) as count
            FROM subscriptions s
            JOIN users u ON s.subscriber_id = u.id
            WHERE {where_sql}
        """
        async with db.execute(count_query, params) as cur:
            row = await cur.fetchone()
            total = row["count"] if row else 0

        query = f"""
            SELECT
                s.*,
                u.user_id,
                u.username
            FROM subscriptions s
            JOIN users u ON s.subscriber_id = u.id
            WHERE {where_sql}
            ORDER BY s.expires_at DESC
            LIMIT ? OFFSET ?
        """
        page_params = params + [limit, offset]
        async with db.execute(query, page_params) as cur:
            rows = await cur.fetchall()

        subscriptions = [dict(row) for row in rows]
        return {
            "items": subscriptions,
            "total": total,
            "page": page,
            "limit": limit,
        }


async def get_subscription_types_statistics():
    """Возвращает статистику по типам активных подписок (trial vs purchased, month vs 3month)."""
    now = int(datetime.datetime.now().timestamp())
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute("""
            SELECT COUNT(*) as count 
            FROM subscriptions 
            WHERE (status = 'trial' OR (status = 'active' AND price = 0))
            AND expires_at > ?
        """, (now,)) as cur:
            row = await cur.fetchone()
            trial_active = row['count'] if row else 0

        async with db.execute("""
            SELECT COUNT(*) as count 
            FROM subscriptions 
            WHERE status = 'active' AND price > 0 AND expires_at > ?
        """, (now,)) as cur:
            row = await cur.fetchone()
            purchased_active = row['count'] if row else 0

        async with db.execute("""
            SELECT COUNT(*) as count 
            FROM subscriptions 
            WHERE status = 'active' AND period = 'month' AND price > 0 AND expires_at > ?
        """, (now,)) as cur:
            row = await cur.fetchone()
            month_active = row['count'] if row else 0

        async with db.execute("""
            SELECT COUNT(*) as count 
            FROM subscriptions 
            WHERE status = 'active' AND period = '3month' AND price > 0 AND expires_at > ?
        """, (now,)) as cur:
            row = await cur.fetchone()
            month3_active = row['count'] if row else 0

        async with db.execute("""
            SELECT COUNT(*) as count 
            FROM subscriptions 
            WHERE status = 'active' AND expires_at > ?
        """, (now,)) as cur:
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
    """Возвращает динамику подписок по дням: trial_active, purchased_active, trial_created, purchased_created."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        now = int(datetime.datetime.now().timestamp())
        start_timestamp = now - (days * 24 * 60 * 60)

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

            for row in rows:
                created_at = row['created_at']
                expires_at = row['expires_at']
                status = row['status']
                price = row['price']
                is_trial = status == 'trial' or price == 0

                if date_timestamp <= created_at < next_date_timestamp:
                    if is_trial:
                        daily_stats['trial_created'] += 1
                    else:
                        daily_stats['purchased_created'] += 1

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


async def get_subscription_conversion_data(days: int = 30):
    """Возвращает данные о конверсии пробных подписок в купленные."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        now = int(datetime.datetime.now().timestamp())
        start_timestamp = now - (days * 24 * 60 * 60)

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

        daily = []
        start_date = datetime.datetime.fromtimestamp(start_timestamp).date()
        end_date = datetime.datetime.now().date()

        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            date_timestamp = int(datetime.datetime.combine(current_date, datetime.time.min).timestamp())
            next_date_timestamp = date_timestamp + 86400

            async with db.execute("""
                SELECT COUNT(DISTINCT subscriber_id) as count
                FROM subscriptions
                WHERE (status = 'trial' OR price = 0)
                AND created_at >= ? AND created_at < ?
            """, (date_timestamp, next_date_timestamp)) as cur:
                row = await cur.fetchone()
                trial_users = row['count'] if row else 0

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


async def upsert_agg_subscriptions_daily() -> int:
    """
    Обновляет агрегаты по подпискам:
    - created_total/paid/trial: по дате created_at
    - active_total/expired_total/deleted_total: snapshot на текущий день
    """
    now = int(time.time())
    today = datetime.datetime.utcfromtimestamp(now).strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT DATE(created_at, 'unixepoch') AS day,
                   COUNT(*) AS created_total,
                   SUM(CASE WHEN price > 0 THEN 1 ELSE 0 END) AS created_paid,
                   SUM(CASE WHEN price <= 0 OR status = 'trial' THEN 1 ELSE 0 END) AS created_trial
            FROM subscriptions
            GROUP BY day
            """
        ) as cur:
            rows = await cur.fetchall()

        updated = 0
        for row in rows:
            day = row["day"]
            if not day:
                continue
            await db.execute(
                """
                INSERT INTO agg_subscriptions_daily
                    (date, created_total, created_paid, created_trial, deleted_total, active_total, expired_total, updated_at)
                VALUES (?, ?, ?, ?, 0, 0, 0, ?)
                ON CONFLICT(date) DO UPDATE SET
                    created_total = excluded.created_total,
                    created_paid = excluded.created_paid,
                    created_trial = excluded.created_trial,
                    updated_at = excluded.updated_at
                """,
                (
                    day,
                    int(row["created_total"] or 0),
                    int(row["created_paid"] or 0),
                    int(row["created_trial"] or 0),
                    now,
                ),
            )
            updated += 1

        async with db.execute(
            """
            SELECT
                SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active_total,
                SUM(CASE WHEN status = 'expired' THEN 1 ELSE 0 END) AS expired_total,
                SUM(CASE WHEN status = 'deleted' THEN 1 ELSE 0 END) AS deleted_total
            FROM subscriptions
            """
        ) as cur:
            snapshot = await cur.fetchone()
        await db.execute(
            """
            INSERT INTO agg_subscriptions_daily
                (date, created_total, created_paid, created_trial, deleted_total, active_total, expired_total, updated_at)
            VALUES (?, 0, 0, 0, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                deleted_total = excluded.deleted_total,
                active_total = excluded.active_total,
                expired_total = excluded.expired_total,
                updated_at = excluded.updated_at
            """,
            (
                today,
                int((snapshot["deleted_total"] if snapshot else 0) or 0),
                int((snapshot["active_total"] if snapshot else 0) or 0),
                int((snapshot["expired_total"] if snapshot else 0) or 0),
                now,
            ),
        )
        await db.commit()
        return updated + 1


async def cleanup_deleted_subscriptions(days: int = 365, *, dry_run: bool = False) -> int:
    cutoff = int((datetime.datetime.now() - datetime.timedelta(days=days)).timestamp())
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT id
            FROM subscriptions
            WHERE status = 'deleted'
              AND (
                    (deleted_at IS NOT NULL AND deleted_at < ?)
                 OR (deleted_at IS NULL AND expires_at < ?)
              )
            """,
            (cutoff, cutoff),
        ) as cur:
            rows = await cur.fetchall()
        candidate_ids = [int(r["id"]) for r in rows]
        if not candidate_ids:
            return 0
        if dry_run:
            logger.info(
                "SUBSCRIPTIONS_CLEANUP_DRY_RUN: would hard-delete %s deleted subscriptions older than %s days",
                len(candidate_ids),
                days,
            )
            return len(candidate_ids)

        placeholders = ",".join("?" for _ in candidate_ids)
        await db.execute(f"DELETE FROM subscription_servers WHERE subscription_id IN ({placeholders})", candidate_ids)
        await db.execute(f"DELETE FROM sent_notifications WHERE subscription_id IN ({placeholders})", candidate_ids)
        await db.execute(f"DELETE FROM subscriptions WHERE id IN ({placeholders})", candidate_ids)
        await db.commit()
        logger.info(
            "SUBSCRIPTIONS_CLEANUP: hard-deleted %s subscriptions older than %s days in deleted status",
            len(candidate_ids),
            days,
        )
        return len(candidate_ids)
