import aiosqlite
import asyncio
import datetime
import logging
import os
import uuid

# База для новой системы подписок
logger = logging.getLogger(__name__)

# Определяем путь к базе данных относительно корня проекта
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

SUBSCRIBERS_DB_PATH = os.path.join(DATA_DIR, "subscribers.db")


async def init_subscribers_db() -> None:
    """Инициализирует БД подписчиков и подписок."""
    async with aiosqlite.connect(SUBSCRIBERS_DB_PATH) as db:
        # Таблица подписчиков (по сути, Telegram-пользователь)
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS subscribers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT UNIQUE NOT NULL,
                created_at INTEGER NOT NULL,
                last_seen INTEGER NOT NULL
            )
            """
        )

        # Таблица подписок (несколько активных подписок на пользователя)
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscriber_id INTEGER NOT NULL,
                status TEXT NOT NULL,          -- active, expired, canceled
                period TEXT NOT NULL,          -- month, 3month
                device_limit INTEGER NOT NULL, -- 1..5
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                subscription_token TEXT UNIQUE NOT NULL,
                price REAL NOT NULL,
                name TEXT,                     -- Имя подписки (для идентификации, например "Для мамы", "Для друга")
                FOREIGN KEY (subscriber_id) REFERENCES subscribers(id)
            )
            """
        )
        
        # Миграция: добавляем поле name если его нет
        try:
            await db.execute("ALTER TABLE subscriptions ADD COLUMN name TEXT")
            logger.info("SUBSCRIBERS_DB: Добавлено поле name в таблицу subscriptions")
        except Exception as e:
            # Поле уже существует или другая ошибка
            if "duplicate column" not in str(e).lower():
                logger.debug(f"SUBSCRIBERS_DB: Поле name уже существует или ошибка: {e}")

        # Таблица связей подписка ↔ сервера XUI
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS subscription_servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscription_id INTEGER NOT NULL,
                server_name TEXT NOT NULL,
                client_email TEXT NOT NULL,
                client_id TEXT,
                FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
            )
            """
        )

        await db.commit()
        logger.info("SUBSCRIBERS_DB: инициализация завершена (%s)", SUBSCRIBERS_DB_PATH)


async def get_or_create_subscriber(user_id: str) -> int:
    """
    Возвращает id подписчика (создаёт, если нет).
    """
    now = int(datetime.datetime.now().timestamp())
    async with aiosqlite.connect(SUBSCRIBERS_DB_PATH) as db:
        # Пытаемся найти
        async with db.execute(
            "SELECT id FROM subscribers WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                subscriber_id = row[0]
                await db.execute(
                    "UPDATE subscribers SET last_seen = ? WHERE id = ?",
                    (now, subscriber_id),
                )
                await db.commit()
                return subscriber_id

        # Создаём нового
        await db.execute(
            """
            INSERT INTO subscribers (user_id, created_at, last_seen)
            VALUES (?, ?, ?)
            """,
            (user_id, now, now),
        )
        await db.commit()

        async with db.execute(
            "SELECT id FROM subscribers WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0]


async def create_subscription(
    subscriber_id: int,
    period: str,
    device_limit: int,
    price: float,
    expires_at: int,
    name: str | None = None,
) -> tuple[int, str]:
    """
    Создаёт запись подписки и возвращает (subscription_id, subscription_token).
    
    Args:
        subscriber_id: ID подписчика
        period: Период подписки (month, 3month)
        device_limit: Лимит устройств
        price: Цена подписки
        expires_at: Unix timestamp времени истечения
        name: Имя подписки (опционально, для идентификации)
    """
    created_at = int(datetime.datetime.now().timestamp())
    token = uuid.uuid4().hex[:24]

    async with aiosqlite.connect(SUBSCRIBERS_DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO subscriptions (
                subscriber_id, status, period, device_limit,
                created_at, expires_at, subscription_token, price, name
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                subscriber_id,
                "active",
                period,
                device_limit,
                created_at,
                expires_at,
                token,
                price,
                name,
            ),
        )
        await db.commit()

        async with db.execute(
            "SELECT id FROM subscriptions WHERE subscription_token = ?", (token,)
        ) as cur:
            row = await cur.fetchone()
            return row[0], token


async def add_subscription_server(
    subscription_id: int, server_name: str, client_email: str, client_id: str | None
) -> int:
    """
    Добавляет связь подписки с конкретным сервером XUI.
    """
    async with aiosqlite.connect(SUBSCRIBERS_DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO subscription_servers (
                subscription_id, server_name, client_email, client_id
            )
            VALUES (?, ?, ?, ?)
            """,
            (subscription_id, server_name, client_email, client_id),
        )
        await db.commit()

        async with db.execute(
            """
            SELECT id FROM subscription_servers
            WHERE subscription_id = ? AND server_name = ? AND client_email = ?
            ORDER BY id DESC LIMIT 1
            """,
            (subscription_id, server_name, client_email),
        ) as cur:
            row = await cur.fetchone()
            return row[0]


async def get_active_subscription_by_user(user_id: str) -> dict | None:
    """
    Возвращает первую активную подписку пользователя (для обратной совместимости).
    Используйте get_all_active_subscriptions_by_user для получения всех подписок.
    """
    subscriptions = await get_all_active_subscriptions_by_user(user_id)
    return subscriptions[0] if subscriptions else None


async def get_all_active_subscriptions_by_user(user_id: str) -> list[dict]:
    """
    Возвращает все активные подписки пользователя.
    """
    async with aiosqlite.connect(SUBSCRIBERS_DB_PATH) as db:
        async with db.execute(
            """
            SELECT s.id, s.status, s.period, s.device_limit,
                   s.created_at, s.expires_at, s.subscription_token, s.price, s.name
            FROM subscriptions s
            JOIN subscribers sub ON s.subscriber_id = sub.id
            WHERE sub.user_id = ? AND s.status = 'active' AND s.expires_at > ?
            ORDER BY s.created_at DESC
            """,
            (user_id, int(datetime.datetime.now().timestamp())),
        ) as cur:
            rows = await cur.fetchall()
            return [
                {
                    "id": row[0],
                    "status": row[1],
                    "period": row[2],
                    "device_limit": row[3],
                    "created_at": row[4],
                    "expires_at": row[5],
                    "subscription_token": row[6],
                    "price": row[7],
                    "name": row[8] or f"Подписка {i+1}",  # Если имя не задано, генерируем автоматически
                }
                for i, row in enumerate(rows)
            ]


async def get_subscription_by_token(token: str) -> dict | None:
    """
    Возвращает подписку по токену (для /sub/<token>).
    """
    async with aiosqlite.connect(SUBSCRIBERS_DB_PATH) as db:
        async with db.execute(
            """
            SELECT s.id, s.status, s.period, s.device_limit,
                   s.created_at, s.expires_at, s.subscription_token, s.price,
                   sub.user_id, s.name
            FROM subscriptions s
            JOIN subscribers sub ON s.subscriber_id = sub.id
            WHERE s.subscription_token = ?
            LIMIT 1
            """,
            (token,),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "status": row[1],
                "period": row[2],
                "device_limit": row[3],
                "created_at": row[4],
                "expires_at": row[5],
                "subscription_token": row[6],
                "price": row[7],
                "user_id": row[8],
                "name": row[9],
            }


async def get_subscription_servers(subscription_id: int) -> list[dict]:
    """
    Возвращает список серверов, привязанных к подписке.
    """
    async with aiosqlite.connect(SUBSCRIBERS_DB_PATH) as db:
        async with db.execute(
            """
            SELECT id, server_name, client_email, client_id
            FROM subscription_servers
            WHERE subscription_id = ?
            ORDER BY id ASC
            """,
            (subscription_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [
                {
                    "id": r[0],
                    "server_name": r[1],
                    "client_email": r[2],
                    "client_id": r[3],
                }
                for r in rows
            ]


async def remove_subscription_server(subscription_id: int, server_name: str) -> bool:
    """
    Удаляет связь подписки с конкретным сервером XUI.
    
    Returns:
        True если сервер был удален, False если не найден
    """
    async with aiosqlite.connect(SUBSCRIBERS_DB_PATH) as db:
        cursor = await db.execute(
            """
            DELETE FROM subscription_servers
            WHERE subscription_id = ? AND server_name = ?
            """,
            (subscription_id, server_name),
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_all_active_subscriptions() -> list[dict]:
    """
    Возвращает все активные подписки.
    """
    async with aiosqlite.connect(SUBSCRIBERS_DB_PATH) as db:
        async with db.execute(
            """
            SELECT s.id, s.status, s.period, s.device_limit,
                   s.created_at, s.expires_at, s.subscription_token, s.price,
                   sub.user_id, s.name
            FROM subscriptions s
            JOIN subscribers sub ON s.subscriber_id = sub.id
            WHERE s.status = 'active' AND s.expires_at > ?
            ORDER BY s.expires_at ASC
            """,
            (int(datetime.datetime.now().timestamp()),),
        ) as cur:
            rows = await cur.fetchall()
            return [
                {
                    "id": r[0],
                    "status": r[1],
                    "period": r[2],
                    "device_limit": r[3],
                    "created_at": r[4],
                    "expires_at": r[5],
                    "subscription_token": r[6],
                    "price": r[7],
                    "user_id": r[8],
                    "name": r[9] or f"Подписка {i+1}",
                }
                for i, r in enumerate(rows)
            ]


async def update_subscription_status(subscription_id: int, status: str) -> None:
    """
    Обновляет статус подписки.
    """
    async with aiosqlite.connect(SUBSCRIBERS_DB_PATH) as db:
        await db.execute(
            "UPDATE subscriptions SET status = ? WHERE id = ?",
            (status, subscription_id),
        )
        await db.commit()


async def update_subscription_expiry(subscription_id: int, new_expires_at: int) -> None:
    """
    Обновляет время истечения подписки.
    """
    async with aiosqlite.connect(SUBSCRIBERS_DB_PATH) as db:
        await db.execute(
            "UPDATE subscriptions SET expires_at = ? WHERE id = ?",
            (new_expires_at, subscription_id),
        )
        await db.commit()


async def get_subscription_by_id(subscription_id: int, user_id: str | None = None) -> dict | None:
    """
    Возвращает подписку по ID.
    Если указан user_id, проверяет, что подписка принадлежит этому пользователю.
    
    Args:
        subscription_id: ID подписки
        user_id: ID пользователя (опционально, для проверки владельца)
    
    Returns:
        Словарь с данными подписки или None, если не найдена или не принадлежит пользователю
    """
    async with aiosqlite.connect(SUBSCRIBERS_DB_PATH) as db:
        if user_id:
            # Проверяем владельца подписки
            async with db.execute(
                """
                SELECT s.id, s.status, s.period, s.device_limit,
                       s.created_at, s.expires_at, s.subscription_token, s.price,
                       sub.user_id, s.name
                FROM subscriptions s
                JOIN subscribers sub ON s.subscriber_id = sub.id
                WHERE s.id = ? AND sub.user_id = ?
                LIMIT 1
                """,
                (subscription_id, user_id),
            ) as cur:
                row = await cur.fetchone()
        else:
            # Без проверки владельца (для админских операций)
            async with db.execute(
                """
                SELECT s.id, s.status, s.period, s.device_limit,
                       s.created_at, s.expires_at, s.subscription_token, s.price,
                       sub.user_id, s.name
                FROM subscriptions s
                JOIN subscribers sub ON s.subscriber_id = sub.id
                WHERE s.id = ?
                LIMIT 1
                """,
                (subscription_id,),
            ) as cur:
                row = await cur.fetchone()
        
        if not row:
            return None
        
        return {
            "id": row[0],
            "status": row[1],
            "period": row[2],
            "device_limit": row[3],
            "created_at": row[4],
            "expires_at": row[5],
            "subscription_token": row[6],
            "price": row[7],
            "user_id": row[8],
            "name": row[9],
        }


async def update_subscription_name(subscription_id: int, new_name: str) -> None:
    """
    Обновляет имя подписки.
    
    Args:
        subscription_id: ID подписки
        new_name: Новое имя подписки
    """
    async with aiosqlite.connect(SUBSCRIBERS_DB_PATH) as db:
        await db.execute(
            "UPDATE subscriptions SET name = ? WHERE id = ?",
            (new_name, subscription_id),
        )
        await db.commit()
        logger.info(f"SUBSCRIBERS_DB: Имя подписки {subscription_id} обновлено на '{new_name}'")


# Для ручного запуска из консоли (инициализация БД)
if __name__ == "__main__":
    asyncio.run(init_subscribers_db())


