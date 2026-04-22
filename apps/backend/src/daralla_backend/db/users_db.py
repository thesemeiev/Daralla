"""
Модуль работы с пользователями и привязкой Telegram.
Таблицы: users, telegram_links, link_telegram_states, known_telegram_ids.
Содержит init_users_db, get_all_user_ids, register_simple_user, is_known_user и все user/telegram-функции.
"""
import aiosqlite
import datetime
import logging
import secrets
import time
import uuid
from . import DB_PATH

logger = logging.getLogger(__name__)

TG_USER_ID_HEX_LEN = 12  # tg_ + 12 hex = 15 символов всего


class UsernameAlreadyExistsError(ValueError):
    """Логин уже занят (веб-регистрация)."""


async def init_users_db():
    """Инициализирует таблицы users, telegram_links, link_telegram_states, known_telegram_ids."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT UNIQUE NOT NULL,
                first_seen INTEGER NOT NULL,
                last_seen INTEGER NOT NULL,
                username TEXT,
                password_hash TEXT,
                is_web INTEGER DEFAULT 0,
                auth_token TEXT,
                telegram_id TEXT
            )
        """)
        await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username) WHERE username IS NOT NULL")
        await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id) WHERE telegram_id IS NOT NULL")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS link_telegram_states (
                state TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS telegram_links (
                telegram_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                linked_at INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_telegram_links_user_id 
            ON telegram_links(user_id)
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS known_telegram_ids (
                telegram_id TEXT PRIMARY KEY,
                first_seen_at INTEGER NOT NULL
            )
        """)

        await db.commit()


USER_ID_HEX_LEN = 12  # usr_ + 12 hex для единого формата


def generate_user_id() -> str:
    """Генерирует уникальный user_id в едином формате (usr_ + 12 hex). Для TG и веб."""
    return f"usr_{uuid.uuid4().hex[:USER_ID_HEX_LEN]}"


def generate_tg_user_id() -> str:
    """Legacy: использует единый формат. Для обратной совместимости."""
    return generate_user_id()


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


async def get_all_user_ids(min_last_seen: int = None) -> list:
    """Возвращает список всех user_id"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
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
    """Регистрирует пользователя (используя единую логику get_or_create_subscriber)."""
    await get_or_create_subscriber(user_id)


async def is_known_user(user_id: str) -> bool:
    """Проверяет наличие пользователя"""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute('SELECT 1 FROM users WHERE user_id = ? LIMIT 1', (user_id,)) as cursor:
                return (await cursor.fetchone()) is not None
    except Exception as e:
        logger.error(f"IS_KNOWN_USER error: {e}")
        return False


async def get_user_by_id(user_id: str):
    """Возвращает информацию о пользователе по user_id"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_user_by_username(username: str):
    """Возвращает пользователя по логину (username), без ограничения is_web."""
    if not username or not username.strip():
        return None
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE LOWER(TRIM(username)) = LOWER(TRIM(?))",
            (username.strip(),),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_user_by_telegram_id(telegram_id: str):
    """Возвращает пользователя по telegram_id (старая логика, напрямую из users)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def _get_user_by_telegram_id_or_user_id_legacy(telegram_id: str):
    """
    Старая логика: сначала ищет по telegram_id (привязанный веб), иначе по user_id (TG-only).
    Используется как fallback в новой схеме.
    """
    user = await get_user_by_telegram_id(telegram_id)
    if user:
        return user
    return await get_user_by_id(telegram_id)


async def get_user_by_telegram_id_v2(telegram_id: str, use_fallback: bool = True):
    """
    Новая логика поиска пользователя по Telegram ID.
    1. Ищет в telegram_links (telegram_id -> users.user_id).
    2. Если не найдено и use_fallback=True - использует старую логику.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT u.*
            FROM telegram_links tl
            JOIN users u ON u.user_id = tl.user_id
            WHERE tl.telegram_id = ?
            """,
            (telegram_id,),
        ) as cur:
            row = await cur.fetchone()
            if row:
                return dict(row)

    if use_fallback:
        return await _get_user_by_telegram_id_or_user_id_legacy(telegram_id)

    return None


async def resolve_user_by_query(query: str):
    """
    Находит пользователя по любому идентификатору: Telegram ID, user_id (usr_) или логин.
    Возвращает dict пользователя или None.
    """
    if not query or not query.strip():
        return None
    q = query.strip()
    if q.isdigit():
        user = await get_user_by_telegram_id_v2(q, use_fallback=True)
        if user:
            return user
        user = await get_user_by_id(q)
        return user
    if q.startswith("usr_"):
        return await get_user_by_id(q)
    user = await get_user_by_username(q)
    if user:
        return user
    return await get_user_by_id(q)


async def get_user_growth_data(days: int = 30):
    """
    Возвращает данные роста пользователей по дням за указанный период.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        now = int(datetime.datetime.now().timestamp())
        start_timestamp = now - (days * 24 * 60 * 60)

        async with db.execute("SELECT COUNT(*) as count FROM users WHERE first_seen < ?", (start_timestamp,)) as cur:
            row = await cur.fetchone()
            users_before_period = row['count'] if row else 0

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


async def get_user_server_usage(user_id: str):
    """
    Возвращает статистику использования серверов пользователем.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
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
        server_usage = {}
        total_usage = 0
        for row in rows:
            server_name = row['server_name']
            usage_count = row['usage_count']
            server_usage[server_name] = usage_count
            total_usage += usage_count
        result = {}
        for server_name, count in server_usage.items():
            percentage = (count / total_usage * 100) if total_usage > 0 else 0
            result[server_name] = {
                'count': count,
                'percentage': round(percentage, 1)
            }
        return result


async def register_web_user(username: str, password_hash: str):
    """Регистрирует нового веб-пользователя (user_id в едином формате usr_xxx)."""
    now = int(datetime.datetime.now().timestamp())
    uname = username.strip().lower()
    if not uname:
        raise ValueError("Логин не может быть пустым")
    existing = await get_user_by_username(uname)
    if existing:
        raise UsernameAlreadyExistsError("Пользователь с таким логином уже существует")
    user_id = generate_user_id()
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """INSERT INTO users (user_id, username, password_hash, is_web, first_seen, last_seen) 
                   VALUES (?, ?, ?, 1, ?, ?)""",
                (user_id, uname, password_hash, now, now)
            )
            await db.commit()
            return user_id
        except aiosqlite.IntegrityError:
            raise UsernameAlreadyExistsError("Пользователь с таким логином уже существует")


async def update_user_auth_token(user_id: str, token: str):
    """Обновляет токен авторизации (для 'запомнить меня')"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET auth_token = ? WHERE user_id = ?", (token, user_id))
        await db.commit()


async def get_user_by_auth_token(token: str):
    """Получает пользователя по токену авторизации"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE auth_token = ?", (token,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_user_by_username_or_id(login: str):
    """Находит пользователя по логину (username) или ТГ ID"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE username = ? OR user_id = ?",
            (login.lower(), login)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def username_available(new_username: str, exclude_user_id: str) -> bool:
    """Проверяет, свободен ли логин."""
    uname = new_username.strip().lower()
    if not uname:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM users WHERE username = ? AND user_id != ?",
            (uname, exclude_user_id),
        ) as cur:
            row = await cur.fetchone()
            return row is None


async def update_user_username(user_id: str, new_username: str):
    """Обновляет логин пользователя."""
    uname = new_username.strip().lower()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET username = ? WHERE user_id = ?",
            (uname, user_id),
        )
        await db.commit()


async def update_user_password(user_id: str, new_password_hash: str):
    """Обновляет пароль пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET password_hash = ? WHERE user_id = ?",
            (new_password_hash, user_id),
        )
        await db.commit()


async def link_telegram_create_state(user_id: str) -> str:
    """Создаёт state для привязки Telegram. Возвращает state."""
    state = secrets.token_hex(16)
    now = int(time.time())
    cutoff = now - 15 * 60
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM link_telegram_states WHERE created_at < ?", (cutoff,))
        await db.execute(
            "INSERT INTO link_telegram_states (state, user_id, created_at) VALUES (?, ?, ?)",
            (state, user_id, now)
        )
        await db.commit()
    return state


async def link_telegram_consume_state(state: str):
    """Возвращает user_id по state и удаляет запись. None если не найден или устарел."""
    cutoff = int(time.time()) - 15 * 60
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id FROM link_telegram_states WHERE state = ? AND created_at >= ?",
            (state, cutoff)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        user_id = row[0]
        await db.execute("DELETE FROM link_telegram_states WHERE state = ?", (state,))
        await db.commit()
        return user_id


async def create_telegram_link(telegram_id: str, user_id: str):
    """Создаёт или обновляет связь TG ↔ аккаунт и помечает TG как известный."""
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO telegram_links (telegram_id, user_id, linked_at)
            VALUES (?, ?, ?)
            """,
            (telegram_id, user_id, now),
        )
        await db.execute(
            """
            INSERT OR IGNORE INTO known_telegram_ids (telegram_id, first_seen_at)
            VALUES (?, ?)
            """,
            (telegram_id, now),
        )
        await db.commit()


async def delete_telegram_link(telegram_id: str):
    """Удаляет связь TG ↔ аккаунт (используется при отвязке)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM telegram_links WHERE telegram_id = ?", (telegram_id,))
        await db.commit()


async def get_telegram_link(telegram_id: str):
    """Возвращает запись из telegram_links по telegram_id."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM telegram_links WHERE telegram_id = ?", (telegram_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def is_known_telegram_id(telegram_id: str) -> bool:
    """Проверяет, известен ли Telegram ID (для контроля выдачи триала)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM known_telegram_ids WHERE telegram_id = ? LIMIT 1",
            (telegram_id,),
        ) as cur:
            row = await cur.fetchone()
            return row is not None


async def mark_telegram_id_known(telegram_id: str):
    """Помечает Telegram ID как известный."""
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO known_telegram_ids (telegram_id, first_seen_at)
            VALUES (?, ?)
            """,
            (telegram_id, now),
        )
        await db.commit()


async def update_user_telegram_id(user_id: str, telegram_id: str | None):
    """Устанавливает или сбрасывает telegram_id у пользователя (поле в users)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET telegram_id = ? WHERE user_id = ?",
            (telegram_id, user_id),
        )
        await db.commit()


async def get_telegram_chat_id_for_notification(user_id: str) -> int | None:
    """
    Возвращает chat_id для отправки в Telegram.
    Единый источник: сначала telegram_links, затем fallback на users.telegram_id и числовой user_id.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT telegram_id FROM telegram_links WHERE user_id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            if row is not None:
                try:
                    return int(row[0])
                except (TypeError, ValueError):
                    pass
    user = await get_user_by_id(user_id)
    if not user:
        return None
    tid = user.get("telegram_id")
    if tid:
        try:
            return int(tid)
        except (TypeError, ValueError):
            pass
    uid = user.get("user_id")
    if uid and isinstance(uid, str) and uid.isdigit():
        return int(uid)
    return None


async def merge_user_into_target(source_user_id: str, target_user_id: str) -> bool:
    """
    Переносит все данные с аккаунта source_user_id на аккаунт target_user_id
    и удаляет исходный аккаунт.
    """
    if source_user_id == target_user_id:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, user_id FROM users WHERE user_id IN (?, ?)",
                (source_user_id, target_user_id),
            ) as cur:
                rows = await cur.fetchall()
            by_uid = {r["user_id"]: r["id"] for r in rows}
            source_id = by_uid.get(source_user_id)
            target_id = by_uid.get(target_user_id)
            if not source_id or not target_id:
                logger.warning(
                    f"merge_user_into_target: пользователь не найден "
                    f"source={source_user_id} (id={source_id}), target={target_user_id} (id={target_id})"
                )
                return False
            await db.execute("BEGIN TRANSACTION")
            await db.execute(
                "UPDATE subscriptions SET subscriber_id = ? WHERE subscriber_id = ?",
                (target_id, source_id),
            )
            await db.execute(
                "UPDATE payments SET user_id = ? WHERE user_id = ?",
                (target_user_id, source_user_id),
            )
            await db.execute(
                "UPDATE sent_notifications SET user_id = ? WHERE user_id = ?",
                (target_user_id, source_user_id),
            )
            await db.execute(
                "UPDATE link_telegram_states SET user_id = ? WHERE user_id = ?",
                (target_user_id, source_user_id),
            )
            await db.execute(
                "DELETE FROM telegram_links WHERE user_id = ?",
                (source_user_id,),
            )
            async with db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='event_counted_payments'"
            ) as cur:
                if await cur.fetchone():
                    await db.execute(
                        "UPDATE event_counted_payments SET referrer_user_id = ? WHERE referrer_user_id = ?",
                        (target_user_id, source_user_id),
                    )
            async with db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_referral_codes'"
            ) as cur:
                if await cur.fetchone():
                    await db.execute(
                        "DELETE FROM user_referral_codes WHERE user_id = ?",
                        (source_user_id,),
                    )
            await db.execute("DELETE FROM users WHERE id = ?", (source_id,))
            await db.commit()
            logger.info(
                f"Аккаунт {source_user_id} объединён с {target_user_id}: данные перенесены, старый аккаунт удалён."
            )
            return True
        except Exception as e:
            await db.rollback()
            logger.error(f"Ошибка merge_user_into_target {source_user_id} -> {target_user_id}: {e}", exc_info=True)
            raise


async def reconcile_users_telegram_id_with_link(telegram_id: str) -> None:
    """
    Приводит колонку users.telegram_id в соответствие с telegram_links.
    Нужна после гонок TG-first регистрации, когда ссылка уже на одном user_id,
    а UNIQUE на telegram_id сорвался на другом.
    """
    row = await get_telegram_link(telegram_id)
    if not row:
        return
    uid = row["user_id"]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET telegram_id = NULL WHERE telegram_id = ? AND user_id != ?",
            (telegram_id, uid),
        )
        await db.execute(
            "UPDATE users SET telegram_id = ? WHERE user_id = ?",
            (telegram_id, uid),
        )
        await db.commit()


async def link_telegram_to_account(telegram_id: str, target_user_id: str) -> dict:
    """
    Единая точка привязки Telegram к аккаунту (target_user_id).
    Returns: {"merged": bool, "previous_user_id": str | None}
    """
    result = {"merged": False, "previous_user_id": None}
    existing = await get_telegram_link(telegram_id)
    previous_owner = None
    if existing and existing.get("user_id") != target_user_id:
        previous_owner = existing["user_id"]
    # Иначе UNIQUE на users.telegram_id: старый владелец ещё держит тот же telegram_id в колонке,
    # пока мы не сбросим его и не запишем на целевой аккаунт.
    if previous_owner:
        await update_user_telegram_id(previous_owner, None)
    await create_telegram_link(telegram_id, target_user_id)
    await update_user_telegram_id(target_user_id, telegram_id)
    if previous_owner:
        await merge_user_into_target(previous_owner, target_user_id)
        result["merged"] = True
        result["previous_user_id"] = previous_owner
    await mark_telegram_id_known(telegram_id)
    return result


async def rename_user_id(old_user_id: str, new_user_id: str) -> bool:
    """Меняет user_id пользователя во всех связанных таблицах."""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("BEGIN TRANSACTION")
            await db.execute(
                "UPDATE users SET user_id = ? WHERE user_id = ?",
                (new_user_id, old_user_id)
            )
            await db.execute(
                "UPDATE payments SET user_id = ? WHERE user_id = ?",
                (new_user_id, old_user_id)
            )
            await db.execute(
                "UPDATE sent_notifications SET user_id = ? WHERE user_id = ?",
                (new_user_id, old_user_id)
            )
            await db.execute(
                "UPDATE link_telegram_states SET user_id = ? WHERE user_id = ?",
                (new_user_id, old_user_id)
            )
            await db.execute(
                "UPDATE telegram_links SET user_id = ? WHERE user_id = ?",
                (new_user_id, old_user_id)
            )
            async with db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='event_counted_payments'"
            ) as cur:
                if await cur.fetchone():
                    await db.execute(
                        "UPDATE event_counted_payments SET referrer_user_id = ? WHERE referrer_user_id = ?",
                        (new_user_id, old_user_id)
                    )
            async with db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_referral_codes'"
            ) as cur:
                if await cur.fetchone():
                    await db.execute(
                        "UPDATE user_referral_codes SET user_id = ? WHERE user_id = ?",
                        (new_user_id, old_user_id)
                    )
            await db.commit()
            logger.info(f"User ID успешно изменен с {old_user_id} на {new_user_id}")
            return True
        except Exception as e:
            await db.rollback()
            logger.error(f"Ошибка при переименовании user_id {old_user_id} -> {new_user_id}: {e}")
            raise


async def delete_user_completely(user_id: str) -> dict:
    """
    Полностью удаляет пользователя и все связанные данные из БД.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        stats = {
            'subscriptions_deleted': 0,
            'subscription_servers_deleted': 0,
            'payments_deleted': 0,
            'sent_notifications_deleted': 0,
            'telegram_links_deleted': 0,
            'link_states_deleted': 0,
            'known_telegram_ids_deleted': 0,
            'event_ref_codes_deleted': 0,
            'event_counted_payments_deleted': 0,
            'user_deleted': False,
            'user_internal_id': None
        }
        try:
            async with db.execute("SELECT id FROM users WHERE user_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
                if not row:
                    logger.warning(f"Пользователь {user_id} не найден в БД")
                    return stats
                user_internal_id = row[0]
                stats['user_internal_id'] = user_internal_id

                async with db.execute(
                    "SELECT id FROM subscriptions WHERE subscriber_id = ?",
                    (user_internal_id,)
                ) as cur:
                    subscription_ids = [row[0] for row in await cur.fetchall()]

                for sub_id in subscription_ids:
                    async with db.execute(
                        "DELETE FROM subscription_servers WHERE subscription_id = ?",
                        (sub_id,)
                    ) as cur:
                        stats['subscription_servers_deleted'] += cur.rowcount

                async with db.execute(
                    "DELETE FROM subscriptions WHERE subscriber_id = ?",
                    (user_internal_id,)
                ) as cur:
                    stats['subscriptions_deleted'] = cur.rowcount

                async with db.execute(
                    "DELETE FROM payments WHERE user_id = ?",
                    (user_id,)
                ) as cur:
                    stats['payments_deleted'] = cur.rowcount

                async with db.execute(
                    "DELETE FROM sent_notifications WHERE user_id = ?",
                    (user_id,),
                ) as cur:
                    stats['sent_notifications_deleted'] = cur.rowcount

                async with db.execute(
                    "DELETE FROM link_telegram_states WHERE user_id = ?",
                    (user_id,),
                ) as cur:
                    stats['link_states_deleted'] = cur.rowcount

                # Читаем telegram_id до удаления user row
                async with db.execute(
                    "SELECT telegram_id FROM users WHERE id = ?",
                    (user_internal_id,),
                ) as cur:
                    user_row = await cur.fetchone()
                    telegram_id = user_row[0] if user_row else None

                async with db.execute(
                    "DELETE FROM telegram_links WHERE user_id = ?",
                    (user_id,),
                ) as cur:
                    stats['telegram_links_deleted'] = cur.rowcount

                if telegram_id:
                    async with db.execute(
                        "DELETE FROM known_telegram_ids WHERE telegram_id = ?",
                        (telegram_id,),
                    ) as cur:
                        stats['known_telegram_ids_deleted'] = cur.rowcount

                # Events module tables (если включены/существуют)
                async with db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_referral_codes'"
                ) as cur:
                    if await cur.fetchone():
                        async with db.execute(
                            "DELETE FROM user_referral_codes WHERE user_id = ?",
                            (user_id,),
                        ) as del_cur:
                            stats['event_ref_codes_deleted'] = del_cur.rowcount

                async with db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='event_counted_payments'"
                ) as cur:
                    if await cur.fetchone():
                        async with db.execute(
                            "DELETE FROM event_counted_payments WHERE referrer_user_id = ?",
                            (user_id,),
                        ) as del_cur:
                            stats['event_counted_payments_deleted'] = del_cur.rowcount

                async with db.execute(
                    "DELETE FROM users WHERE id = ?",
                    (user_internal_id,)
                ) as cur:
                    if cur.rowcount > 0:
                        stats['user_deleted'] = True

                await db.commit()
                logger.info(
                    f"Пользователь {user_id} полностью удален: "
                    f"{stats['subscriptions_deleted']} подписок, "
                    f"{stats['subscription_servers_deleted']} связей с серверами, "
                    f"{stats['payments_deleted']} платежей, "
                    f"{stats['sent_notifications_deleted']} уведомлений, "
                    f"{stats['telegram_links_deleted']} telegram_links"
                )
        except Exception as e:
            logger.error(f"Ошибка удаления пользователя {user_id}: {e}", exc_info=True)
            await db.rollback()
            raise
        return stats


async def cleanup_inactive_users(days: int = 365, *, dry_run: bool = False) -> int:
    """
    Удаляет пользователей без активности старше days, у которых нет активных подписок.
    """
    cutoff = int(time.time()) - (days * 24 * 60 * 60)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT u.user_id
            FROM users u
            WHERE u.last_seen < ?
              AND NOT EXISTS (
                    SELECT 1
                    FROM subscriptions s
                    WHERE s.subscriber_id = u.id
                      AND s.status = 'active'
                      AND s.expires_at > strftime('%s', 'now')
                )
            """,
            (cutoff,),
        ) as cur:
            rows = await cur.fetchall()
    candidates = [r["user_id"] for r in rows]
    if not candidates:
        return 0
    if dry_run:
        logger.info(
            "INACTIVE_USERS_CLEANUP_DRY_RUN: would delete %s users inactive > %s days",
            len(candidates),
            days,
        )
        return len(candidates)
    deleted = 0
    for user_id in candidates:
        try:
            stats = await delete_user_completely(user_id)
            if stats.get("user_deleted"):
                deleted += 1
        except Exception as e:
            logger.warning("Ошибка удаления неактивного пользователя %s: %s", user_id, e)
    return deleted
