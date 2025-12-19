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
