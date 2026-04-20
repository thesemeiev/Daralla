"""
Запросы к БД модуля событий (рефералы, события, засчитанные оплаты).
"""
import json
import logging
import random
import string
from datetime import datetime, timezone
import aiosqlite

from bot.db import DB_PATH

logger = logging.getLogger(__name__)


def _now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _generate_referral_code(length: int = 6) -> str:
    """Генерирует случайный код из A-Z, 0-9."""
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=length))


async def get_or_create_referral_code(user_id: str) -> str:
    """Возвращает реферальный код пользователя, создаёт при отсутствии (6 символов A-Z, 0-9)."""
    if not user_id:
        raise ValueError("user_id required")
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT code FROM user_referral_codes WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        if row:
            return row[0]
        now = _now_iso()
        for _ in range(10):
            code = _generate_referral_code()
            try:
                await db.execute(
                    "INSERT INTO user_referral_codes (user_id, code, created_at) VALUES (?, ?, ?)",
                    (user_id, code, now),
                )
                await db.commit()
                return code
            except aiosqlite.IntegrityError:
                await db.rollback()
                continue
        raise RuntimeError("Failed to generate unique referral code")


async def get_user_id_by_code(code: str) -> str | None:
    """По коду возвращает user_id реферера или None."""
    if not code:
        return None
    code = code.strip().upper()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT user_id FROM user_referral_codes WHERE code = ?",
            (code,),
        )
        row = await cursor.fetchone()
        return row[0] if row else None


async def get_user_first_seen(user_id: str) -> int | None:
    """Возвращает first_seen (unix timestamp) пользователя из users или None."""
    if not user_id:
        return None
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "SELECT first_seen FROM users WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            return row[0] if row else None
    except Exception:
        return None


# --- CRUD событий ---

async def create_event(name: str, description: str, start_at: str, end_at: str, rewards_json: str | None = None, status: str = "active") -> int:
    """Создаёт событие. rewards_json — JSON строка, например '[{"place":1,"days":100}]'. Возвращает id."""
    created_at = _now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO events (name, description, start_at, end_at, rewards_json, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name, description or "", start_at, end_at, rewards_json or "[]", status, created_at),
        )
        await db.commit()
        return cursor.lastrowid


async def get_event_by_id(event_id: int) -> dict | None:
    """Возвращает событие по id или None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM events WHERE id = ?", (event_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("rewards_json"):
            try:
                d["rewards"] = json.loads(d["rewards_json"])
            except Exception:
                d["rewards"] = []
        else:
            d["rewards"] = []
        return d


async def list_events_active(now_iso: str | None = None) -> list:
    """События, у которых start_at <= now <= end_at."""
    now = now_iso or _now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM events WHERE start_at <= ? AND end_at >= ? AND status != 'draft' ORDER BY start_at ASC",
            (now, now),
        )
        rows = await cursor.fetchall()
        return [_event_row_to_dict(r) for r in rows]


async def list_events_upcoming(now_iso: str | None = None) -> list:
    """События, у которых start_at > now."""
    now = now_iso or _now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM events WHERE start_at > ? AND status != 'draft' ORDER BY start_at ASC",
            (now,),
        )
        rows = await cursor.fetchall()
        return [_event_row_to_dict(r) for r in rows]


async def list_events_ended(now_iso: str | None = None) -> list:
    """События, у которых end_at < now."""
    now = now_iso or _now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM events WHERE end_at < ? ORDER BY end_at DESC",
            (now,),
        )
        rows = await cursor.fetchall()
        return [_event_row_to_dict(r) for r in rows]


async def list_events_all() -> list:
    """Все события (для админки)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM events ORDER BY start_at DESC")
        rows = await cursor.fetchall()
        return [_event_row_to_dict(r) for r in rows]


async def update_event(event_id: int, name: str | None = None, description: str | None = None,
                      start_at: str | None = None, end_at: str | None = None,
                      rewards_json: str | None = None, status: str | None = None) -> bool:
    """Обновляет событие. Переданные поля обновляются, остальные не меняются."""
    updates = []
    params = []
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if start_at is not None:
        updates.append("start_at = ?")
        params.append(start_at)
    if end_at is not None:
        updates.append("end_at = ?")
        params.append(end_at)
    if rewards_json is not None:
        updates.append("rewards_json = ?")
        params.append(rewards_json)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if not updates:
        return True
    params.append(event_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE events SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        await db.commit()
        return True


async def delete_event(event_id: int) -> bool:
    """Удаляет событие по id и все связанные записи (оплаты, награды). Возвращает True если удалено."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM event_counted_payments WHERE event_id = ?", (event_id,))
        await db.execute("DELETE FROM event_rewards_granted WHERE event_id = ?", (event_id,))
        cursor = await db.execute("DELETE FROM events WHERE id = ?", (event_id,))
        await db.commit()
        return cursor.rowcount > 0 if cursor.rowcount is not None else True


def _event_row_to_dict(row, now_iso: str | None = None) -> dict:
    d = dict(row)
    if d.get("rewards_json"):
        try:
            d["rewards"] = json.loads(d["rewards_json"])
        except Exception:
            d["rewards"] = []
    else:
        d["rewards"] = []
    # Вычисляемый статус по датам: active | upcoming | ended
    now = now_iso or _now_iso()
    start = d.get("start_at") or ""
    end = d.get("end_at") or ""
    if start and end:
        if start <= now <= end:
            d["computed_status"] = "active"
        elif now < start:
            d["computed_status"] = "upcoming"
        else:
            d["computed_status"] = "ended"
    else:
        d["computed_status"] = "ended"
    return d


# --- Рейтинг по событию (event_counted_payments) ---

def _display_name(row) -> str:
    """Для рейтинга: логин если есть, иначе user_id."""
    uid = row.get("referrer_user_id") or ""
    username = (row.get("username") or "").strip()
    return username if username else uid


async def get_leaderboard(event_id: int, limit: int = 10) -> list:
    """
    Топ рефереров по событию: по event_counted_payments считаем оплаты с кодом.
    Возвращает список { referrer_user_id, account_id, count, place }.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT ecp.referrer_user_id, MAX(u.username) AS username, COUNT(ecp.id) AS cnt
            FROM event_counted_payments ecp
            LEFT JOIN users u ON u.user_id = ecp.referrer_user_id
            WHERE ecp.event_id = ?
            GROUP BY ecp.referrer_user_id
            ORDER BY cnt DESC
            LIMIT ?
            """,
            (event_id, limit),
        )
        rows = await cursor.fetchall()
        result = []
        for i, r in enumerate(rows, 1):
            uid = r["referrer_user_id"] or ""
            result.append({
                "referrer_user_id": uid,
                "account_id": _display_name(dict(r)),
                "count": r["cnt"],
                "place": i
            })
        return result


async def get_leaderboard_with_places(event_id: int, limit: int = 100) -> list:
    """
    Топ рефереров с учётом ничьих: одинаковый count = одинаковое place.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT ecp.referrer_user_id, MAX(u.username) AS username, COUNT(ecp.id) AS cnt
            FROM event_counted_payments ecp
            LEFT JOIN users u ON u.user_id = ecp.referrer_user_id
            WHERE ecp.event_id = ?
            GROUP BY ecp.referrer_user_id
            ORDER BY cnt DESC
            LIMIT ?
            """,
            (event_id, limit),
        )
        rows = await cursor.fetchall()
        result = []
        place = 1
        prev_count = None
        for r in rows:
            cnt = r["cnt"]
            uid = r["referrer_user_id"] or ""
            if prev_count is not None and cnt < prev_count:
                place = len(result) + 1
            prev_count = cnt
            result.append({
                "referrer_user_id": uid,
                "account_id": _display_name(dict(r)),
                "count": cnt,
                "place": place
            })
        return result


async def is_rewards_granted(event_id: int) -> bool:
    """Проверяет, выданы ли уже награды по событию."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT 1 FROM event_rewards_granted WHERE event_id = ?", (event_id,))
        row = await cursor.fetchone()
        return row is not None


async def set_rewards_granted(event_id: int) -> None:
    """Отмечает, что награды по событию выданы."""
    now = _now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO event_rewards_granted (event_id, granted_at) VALUES (?, ?)",
            (event_id, now),
        )
        await db.commit()


async def get_my_place(event_id: int, user_id: str) -> dict | None:
    """
    Место текущего пользователя (как реферера) в рейтинге по событию и его count.
    Возвращает { place, count } или None если пользователь не в рейтинге.
    """
    leaderboard = await get_leaderboard(event_id, limit=10000)
    for i, row in enumerate(leaderboard, 1):
        if row["referrer_user_id"] == user_id:
            return {"place": i, "count": row["count"]}
    return None


# --- Засчёт оплаты для рейтинга (on_payment_success) ---

async def add_counted_payment(event_id: int, referrer_user_id: str, payment_id: str) -> None:
    """Добавляет одну запись в event_counted_payments (идемпотентно: INSERT OR IGNORE по UNIQUE)."""
    now = _now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """
                INSERT OR IGNORE INTO event_counted_payments (event_id, referrer_user_id, payment_id, paid_at)
                VALUES (?, ?, ?, ?)
                """,
                (event_id, referrer_user_id, payment_id, now),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
