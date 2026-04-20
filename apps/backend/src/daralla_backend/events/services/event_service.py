"""
Сервис событий: обёртки над queries, проверка дат.
"""
import json
import logging
from datetime import datetime, timezone
from bot.events.db.queries import (
    create_event as db_create_event,
    get_event_by_id,
    list_events_active,
    list_events_upcoming,
    list_events_ended,
    list_events_all,
    update_event as db_update_event,
    delete_event as db_delete_event,
)

logger = logging.getLogger(__name__)


def _parse_datetime(s: str) -> tuple[str, str] | None:
    """Парсит дату/время из календаря админки или ISO. Возвращает (raw, нормализованная строка …Z) или None."""
    if not s or not isinstance(s, str):
        return None
    raw = s.strip()
    if not raw:
        return None
    s = raw
    if "." in s:
        s = s.split(".", 1)[0]
    if "T" not in s and len(s) >= 11 and s[10:11] == " ":
        s = s[:10] + "T" + s[11:].lstrip()
    s = s.removesuffix("Z").removesuffix("z")
    # Смещение +03:00 / -05:00 — fromisoformat; в БД пишем UTC-наивную метку с суффиксом Z (как раньше).
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        dt = None
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(s[:19] if len(s) >= 19 else s, fmt)
                break
            except (ValueError, TypeError):
                continue
        if dt is None:
            return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    iso = dt.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    return (raw, iso)


async def create_event(name: str, description: str, start_at: str, end_at: str, rewards: list | None = None, status: str = "active") -> int:
    """Создаёт событие. rewards — список {place, description}. Валидирует даты. Возвращает id."""
    parsed_start = _parse_datetime(start_at)
    parsed_end = _parse_datetime(end_at)
    if not parsed_start or not parsed_end:
        raise ValueError("Неверный формат даты или времени. Выберите начало и окончание в календаре.")
    _, start_iso = parsed_start
    _, end_iso = parsed_end
    if start_iso >= end_iso:
        raise ValueError("Дата начала должна быть раньше даты окончания.")
    rewards_json = json.dumps(rewards or [])
    return await db_create_event(name, description or "", start_iso, end_iso, rewards_json=rewards_json, status=status)


async def get_event(event_id: int):
    return await get_event_by_id(event_id)


async def list_active():
    return await list_events_active()


async def list_upcoming():
    return await list_events_upcoming()


async def list_ended():
    return await list_events_ended()


async def list_all():
    return await list_events_all()


async def update_event(event_id: int, name: str | None = None, description: str | None = None,
                      start_at: str | None = None, end_at: str | None = None,
                      rewards: list | None = None, status: str | None = None) -> bool:
    """Обновляет событие. Рефералы и рейтинги не затрагиваются."""
    rewards_json = json.dumps(rewards) if rewards is not None else None
    if start_at is not None:
        parsed = _parse_datetime(start_at)
        if not parsed:
            raise ValueError("Неверный формат даты начала. Выберите значение в календаре.")
        start_at = parsed[1]
    if end_at is not None:
        parsed = _parse_datetime(end_at)
        if not parsed:
            raise ValueError("Неверный формат даты окончания. Выберите значение в календаре.")
        end_at = parsed[1]
    ev = await get_event_by_id(event_id)
    if not ev:
        return False
    # Проверка start < end при обновлении
    s = start_at if start_at is not None else ev.get("start_at")
    e = end_at if end_at is not None else ev.get("end_at")
    if s and e and s >= e:
        raise ValueError("Дата начала должна быть раньше даты окончания.")
    return await db_update_event(event_id, name=name, description=description, start_at=start_at,
                                 end_at=end_at, rewards_json=rewards_json, status=status)


async def delete_event(event_id: int) -> bool:
    return await db_delete_event(event_id)
