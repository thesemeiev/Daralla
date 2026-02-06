"""
Account + Identity storage (SQLite). Remnawave is the source of truth for subscriptions.

Local DB: accounts, identities, account_remnawave, account_web_credentials,
link_telegram_states, account_auth_tokens, account_expiry_cache.
"""

from __future__ import annotations

import aiosqlite
import datetime
import logging
import secrets
import time
from typing import Any, Optional

from . import DB_PATH

logger = logging.getLogger(__name__)


async def init_accounts_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                account_id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at INTEGER NOT NULL,
                last_seen INTEGER NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS identities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                provider TEXT NOT NULL,
                provider_user_id TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                UNIQUE(provider, provider_user_id),
                FOREIGN KEY(account_id) REFERENCES accounts(account_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS account_remnawave (
                account_id INTEGER PRIMARY KEY,
                remnawave_user_uuid TEXT UNIQUE NOT NULL,
                remnawave_short_uuid TEXT UNIQUE,
                linked_at INTEGER NOT NULL,
                FOREIGN KEY(account_id) REFERENCES accounts(account_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS account_web_credentials (
                account_id INTEGER PRIMARY KEY,
                password_hash TEXT NOT NULL,
                FOREIGN KEY(account_id) REFERENCES accounts(account_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS link_telegram_states (
                state TEXT PRIMARY KEY,
                account_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY(account_id) REFERENCES accounts(account_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS account_auth_tokens (
                token TEXT PRIMARY KEY,
                account_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY(account_id) REFERENCES accounts(account_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS account_expiry_cache (
                account_id INTEGER PRIMARY KEY,
                expires_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY(account_id) REFERENCES accounts(account_id)
            )
            """
        )
        await db.commit()


def _now_ts() -> int:
    return int(datetime.datetime.now().timestamp())


async def create_account() -> int:
    now = _now_ts()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO accounts (created_at, last_seen) VALUES (?, ?)",
            (now, now),
        )
        await db.commit()
        return int(cur.lastrowid or 0)


async def touch_account(account_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE accounts SET last_seen = ? WHERE account_id = ?", (_now_ts(), int(account_id)))
        await db.commit()


async def get_account_id_by_identity(provider: str, provider_user_id: str) -> Optional[int]:
    if not provider or not provider_user_id:
        return None
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT account_id FROM identities WHERE provider = ? AND provider_user_id = ?",
            (provider, str(provider_user_id)),
        ) as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else None


async def link_identity(account_id: int, provider: str, provider_user_id: str) -> None:
    if not provider or not provider_user_id:
        raise ValueError("provider/provider_user_id required")
    now = _now_ts()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO identities (account_id, provider, provider_user_id, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (int(account_id), provider, str(provider_user_id), now),
        )
        await db.commit()


async def get_or_create_account_for_telegram(telegram_id: str) -> int:
    tid = str(telegram_id)
    existing = await get_account_id_by_identity("telegram", tid)
    if existing:
        await touch_account(existing)
        return existing
    account_id = await create_account()
    await link_identity(account_id, "telegram", tid)
    return account_id


async def get_or_create_account_for_username(username: str) -> int:
    uname = (username or "").strip().lower()
    if not uname:
        raise ValueError("username required")
    existing = await get_account_id_by_identity("password", uname)
    if existing:
        await touch_account(existing)
        return existing
    account_id = await create_account()
    await link_identity(account_id, "password", uname)
    return account_id


async def set_remnawave_mapping(account_id: int, remnawave_user_uuid: str, remnawave_short_uuid: str | None = None) -> None:
    if not remnawave_user_uuid:
        raise ValueError("remnawave_user_uuid required")
    now = _now_ts()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO account_remnawave (account_id, remnawave_user_uuid, remnawave_short_uuid, linked_at)
            VALUES (?, ?, ?, ?)
            """,
            (int(account_id), str(remnawave_user_uuid), str(remnawave_short_uuid) if remnawave_short_uuid else None, now),
        )
        await db.commit()


async def get_remnawave_mapping(account_id: int) -> Optional[dict[str, Any]]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM account_remnawave WHERE account_id = ?",
            (int(account_id),),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_telegram_id_for_account(account_id: int) -> Optional[str]:
    """Возвращает telegram_id для аккаунта (для отправки сообщений в бот)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT provider_user_id FROM identities WHERE account_id = ? AND provider = ?",
            (int(account_id), "telegram"),
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def get_username_for_account(account_id: int) -> Optional[str]:
    """Возвращает username (логин) для аккаунта, если есть identity password."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT provider_user_id FROM identities WHERE account_id = ? AND provider = ?",
            (int(account_id), "password"),
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def delete_identity(account_id: int, provider: str, provider_user_id: str) -> None:
    """Удаляет одну запись identity для аккаунта."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM identities WHERE account_id = ? AND provider = ? AND provider_user_id = ?",
            (int(account_id), provider, str(provider_user_id)),
        )
        await db.commit()


async def replace_password_identity(account_id: int, new_username: str) -> None:
    """Меняет логин (identity provider=password) для аккаунта: удаляет старую, добавляет новую."""
    new_username = (new_username or "").strip().lower()
    if not new_username:
        raise ValueError("new_username required")
    now = _now_ts()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM identities WHERE account_id = ? AND provider = ?",
            (int(account_id), "password"),
        )
        await db.execute(
            "INSERT INTO identities (account_id, provider, provider_user_id, created_at) VALUES (?, ?, ?, ?)",
            (int(account_id), "password", new_username, now),
        )
        await db.commit()


# ---- Web credentials (password for login) ----

async def set_account_password(account_id: int, password_hash: str) -> None:
    """Устанавливает или обновляет пароль для аккаунта (веб-доступ)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO account_web_credentials (account_id, password_hash) VALUES (?, ?)",
            (int(account_id), password_hash),
        )
        await db.commit()


async def get_account_password_hash(account_id: int) -> Optional[str]:
    """Возвращает хэш пароля аккаунта или None."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT password_hash FROM account_web_credentials WHERE account_id = ?",
            (int(account_id),),
        ) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def username_available(new_username: str, exclude_account_id: Optional[int] = None) -> bool:
    """Проверяет, свободен ли логин (никто, кроме exclude_account_id, им не пользуется)."""
    uname = (new_username or "").strip().lower()
    if not uname:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        if exclude_account_id is not None:
            async with db.execute(
                "SELECT 1 FROM identities WHERE provider = ? AND provider_user_id = ? AND account_id != ?",
                ("password", uname, int(exclude_account_id)),
            ) as cur:
                return (await cur.fetchone()) is None
        async with db.execute(
            "SELECT 1 FROM identities WHERE provider = ? AND provider_user_id = ?",
            ("password", uname),
        ) as cur:
            return (await cur.fetchone()) is None


# ---- Link Telegram state ----

async def link_telegram_create_state(account_id: int) -> str:
    """Создаёт state для привязки Telegram. Возвращает state."""
    state = secrets.token_hex(16)
    now = int(time.time())
    cutoff = now - 15 * 60
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM link_telegram_states WHERE created_at < ?", (cutoff,))
        await db.execute(
            "INSERT INTO link_telegram_states (state, account_id, created_at) VALUES (?, ?, ?)",
            (state, int(account_id), now),
        )
        await db.commit()
    return state


async def link_telegram_consume_state(state: str) -> Optional[str]:
    """Возвращает account_id (как строку) по state и удаляет запись. None если не найден."""
    cutoff = int(time.time()) - 15 * 60
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT account_id FROM link_telegram_states WHERE state = ? AND created_at >= ?",
            (state, cutoff),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        account_id = str(row[0])
        await db.execute("DELETE FROM link_telegram_states WHERE state = ?", (state,))
        await db.commit()
        return account_id


# ---- Auth tokens (remember me) ----

async def set_account_auth_token(account_id: int, token: str) -> None:
    """Сохраняет токен авторизации для аккаунта."""
    now = _now_ts()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO account_auth_tokens (token, account_id, created_at) VALUES (?, ?, ?)",
            (token, int(account_id), now),
        )
        await db.commit()


async def get_account_id_by_auth_token(token: str) -> Optional[int]:
    """Возвращает account_id по токену или None."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT account_id FROM account_auth_tokens WHERE token = ?",
            (token,),
        ) as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else None


# ---- Expiry cache (for notifications; updated when Remnawave expiry changes) ----

async def upsert_account_expiry_cache(account_id: int, expires_at: int) -> None:
    """Обновляет кэш срока подписки для уведомлений."""
    now = _now_ts()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO account_expiry_cache (account_id, expires_at, updated_at) VALUES (?, ?, ?)",
            (int(account_id), expires_at, now),
        )
        await db.commit()


async def get_accounts_expiring_soon(
    now_ts: int,
    window_1h: int = 3600,
    window_1d: int = 86400,
    window_3d: int = 259200,
) -> list[dict[str, Any]]:
    """Возвращает аккаунты с истекающей подпиской в заданных окнах (секунды до истечения)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT account_id, expires_at FROM account_expiry_cache
            WHERE expires_at > ? AND expires_at <= ?
            ORDER BY expires_at
            """,
            (now_ts, now_ts + window_3d),
        ) as cur:
            rows = await cur.fetchall()
    return [{"account_id": r["account_id"], "expires_at": r["expires_at"]} for r in rows]


async def get_telegram_chat_id_for_account(account_id: int) -> Optional[int]:
    """Возвращает chat_id (int) для уведомлений по account_id."""
    tid = await get_telegram_id_for_account(account_id)
    if not tid:
        return None
    try:
        return int(tid)
    except (TypeError, ValueError):
        return None


async def delete_account(account_id: int) -> None:
    """Удаляет аккаунт и все связанные данные."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM account_expiry_cache WHERE account_id = ?", (account_id,))
        await db.execute("DELETE FROM account_auth_tokens WHERE account_id = ?", (account_id,))
        await db.execute("DELETE FROM link_telegram_states WHERE account_id = ?", (account_id,))
        await db.execute("DELETE FROM account_web_credentials WHERE account_id = ?", (account_id,))
        await db.execute("DELETE FROM account_remnawave WHERE account_id = ?", (account_id,))
        await db.execute("DELETE FROM identities WHERE account_id = ?", (account_id,))
        await db.execute("DELETE FROM accounts WHERE account_id = ?", (account_id,))
        await db.commit()


async def get_all_account_ids(min_last_seen: int | None = None) -> list[str]:
    """Возвращает список всех account_id (как строки)."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            if min_last_seen is not None:
                async with db.execute(
                    "SELECT account_id FROM accounts WHERE last_seen >= ? ORDER BY last_seen DESC",
                    (min_last_seen,),
                ) as cur:
                    rows = await cur.fetchall()
            else:
                async with db.execute("SELECT account_id FROM accounts ORDER BY last_seen DESC") as cur:
                    rows = await cur.fetchall()
            return [str(row[0]) for row in rows]
    except Exception as e:
        logger.error("get_all_account_ids error: %s", e)
        return []
