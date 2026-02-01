"""
Запросы к БД модуля событий (рефералы, события, засчитанные оплаты).
"""
import json
import logging
from datetime import datetime
import aiosqlite

from bot.db import DB_PATH

logger = logging.getLogger(__name__)


def _now_iso():
    return datetime.utcnow().isoformat() + "Z"


async def record_referral(referrer_user_id: str, referred_user_id: str, event_id: int | None = None) -> bool:
    """
    Записывает реферальную связь. Первый реферер выигрывает: если для (referred_user_id, event_id)
    уже есть запись, вставка не выполняется (UNIQUE).
    Возвращает True если запись добавлена, False если уже существовала.
    """
    if not referrer_user_id or not referred_user_id or referrer_user_id == referred_user_id:
        return False
    now = _now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """
                INSERT INTO event_referrals (event_id, referrer_user_id, referred_user_id, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (event_id, referrer_user_id, referred_user_id, now),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            # UNIQUE(referred_user_id, event_id) — уже есть запись
            await db.rollback()
            return False


async def get_referrer_for_user(referred_user_id: str, event_id: int | None = None):
    """
    Возвращает реферера для приглашённого. event_id=None — глобальная связь (любая запись с event_id IS NULL).
    Возвращает dict с referrer_user_id, created_at или None.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if event_id is None:
            await db.execute(
                """
                SELECT referrer_user_id, created_at FROM event_referrals
                WHERE referred_user_id = ? AND event_id IS NULL
                ORDER BY created_at ASC LIMIT 1
                """,
                (referred_user_id,),
            )
        else:
            await db.execute(
                """
                SELECT referrer_user_id, created_at FROM event_referrals
                WHERE referred_user_id = ? AND event_id = ?
                LIMIT 1
                """,
                (referred_user_id, event_id),
            )
        row = await db.fetchone()
        return dict(row) if row else None


async def list_referrals_by_referrer(referrer_user_id: str, event_id: int | None = None):
    """Список приглашённых по рефереру. event_id=None — все записи этого реферера с event_id IS NULL."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if event_id is None:
            await db.execute(
                """
                SELECT referred_user_id, created_at FROM event_referrals
                WHERE referrer_user_id = ? AND event_id IS NULL
                ORDER BY created_at DESC
                """,
                (referrer_user_id,),
            )
        else:
            await db.execute(
                """
                SELECT referred_user_id, created_at FROM event_referrals
                WHERE referrer_user_id = ? AND event_id = ?
                ORDER BY created_at DESC
                """,
                (referrer_user_id, event_id),
            )
        rows = await db.fetchall()
        return [dict(r) for r in rows]


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
        await db.execute("SELECT * FROM events WHERE id = ?", (event_id,))
        row = await db.fetchone()
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
        await db.execute(
            "SELECT * FROM events WHERE start_at <= ? AND end_at >= ? AND status != 'draft' ORDER BY start_at ASC",
            (now, now),
        )
        rows = await db.fetchall()
        return [_event_row_to_dict(r) for r in rows]


async def list_events_upcoming(now_iso: str | None = None) -> list:
    """События, у которых start_at > now."""
    now = now_iso or _now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "SELECT * FROM events WHERE start_at > ? AND status != 'draft' ORDER BY start_at ASC",
            (now,),
        )
        rows = await db.fetchall()
        return [_event_row_to_dict(r) for r in rows]


async def list_events_ended(now_iso: str | None = None) -> list:
    """События, у которых end_at < now."""
    now = now_iso or _now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            "SELECT * FROM events WHERE end_at < ? ORDER BY end_at DESC",
            (now,),
        )
        rows = await db.fetchall()
        return [_event_row_to_dict(r) for r in rows]


async def list_events_all() -> list:
    """Все события (для админки)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("SELECT * FROM events ORDER BY start_at DESC")
        rows = await db.fetchall()
        return [_event_row_to_dict(r) for r in rows]


async def delete_event(event_id: int) -> bool:
    """Удаляет событие по id. Возвращает True если удалено."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM events WHERE id = ?", (event_id,))
        await db.commit()
        return cursor.rowcount > 0 if cursor.rowcount is not None else True


def _event_row_to_dict(row) -> dict:
    d = dict(row)
    if d.get("rewards_json"):
        try:
            d["rewards"] = json.loads(d["rewards_json"])
        except Exception:
            d["rewards"] = []
    else:
        d["rewards"] = []
    return d


# --- Рейтинг по событию (event_counted_payments + event_referrals) ---

async def get_leaderboard(event_id: int, limit: int = 10) -> list:
    """
    Топ рефереров по событию: по event_counted_payments считаем засчитанные оплаты
    приглашённых, группируем по referrer (через event_referrals). Возвращает список
    { referrer_user_id, count, place } с place 1, 2, 3, ... (без учёта ничьих).
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            """
            SELECT er.referrer_user_id, COUNT(ecp.id) AS cnt
            FROM event_counted_payments ecp
            JOIN event_referrals er ON er.referred_user_id = ecp.referred_user_id AND er.event_id = ecp.event_id
            WHERE ecp.event_id = ?
            GROUP BY er.referrer_user_id
            ORDER BY cnt DESC
            LIMIT ?
            """,
            (event_id, limit),
        )
        rows = await db.fetchall()
        result = []
        for i, r in enumerate(rows, 1):
            result.append({"referrer_user_id": r["referrer_user_id"], "count": r["cnt"], "place": i})
        return result


async def get_leaderboard_with_places(event_id: int, limit: int = 100) -> list:
    """
    Топ рефереров с учётом ничьих: одинаковый count = одинаковое place.
    Возвращает список { referrer_user_id, count, place }.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            """
            SELECT er.referrer_user_id, COUNT(ecp.id) AS cnt
            FROM event_counted_payments ecp
            JOIN event_referrals er ON er.referred_user_id = ecp.referred_user_id AND er.event_id = ecp.event_id
            WHERE ecp.event_id = ?
            GROUP BY er.referrer_user_id
            ORDER BY cnt DESC
            LIMIT ?
            """,
            (event_id, limit),
        )
        rows = await db.fetchall()
        result = []
        place = 1
        prev_count = None
        for r in rows:
            cnt = r["cnt"]
            if prev_count is not None and cnt < prev_count:
                place = len(result) + 1
            prev_count = cnt
            result.append({"referrer_user_id": r["referrer_user_id"], "count": cnt, "place": place})
        return result


async def is_rewards_granted(event_id: int) -> bool:
    """Проверяет, выданы ли уже награды по событию."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("SELECT 1 FROM event_rewards_granted WHERE event_id = ?", (event_id,))
        row = await db.fetchone()
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

async def get_active_event_ids_for_referred_user(referred_user_id: str) -> list:
    """Список id активных событий, в которых referred_user_id участвует как приглашённый."""
    now = _now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            SELECT DISTINCT er.event_id FROM event_referrals er
            JOIN events e ON e.id = er.event_id
            WHERE er.referred_user_id = ? AND er.event_id IS NOT NULL
              AND e.start_at <= ? AND e.end_at >= ? AND e.status != 'draft'
            """,
            (referred_user_id, now, now),
        )
        rows = await db.fetchall()
        return [r[0] for r in rows] if rows else []


async def add_counted_payment(event_id: int, referred_user_id: str) -> None:
    """Добавляет одну запись в event_counted_payments (идемпотентно: INSERT OR IGNORE по UNIQUE)."""
    now = _now_iso()
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """
                INSERT OR IGNORE INTO event_counted_payments (event_id, referred_user_id, paid_at)
                VALUES (?, ?, ?)
                """,
                (event_id, referred_user_id, now),
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
