"""
Сервис событий: обёртки над queries, проверка дат.
"""
import json
import logging
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
    """Парсит дату в формате YYYY-MM-DD HH:MM или YYYY-MM-DDTHH:MM. Возвращает (raw, normalized_iso) или None."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            from datetime import datetime
            dt = datetime.strptime(s[:19] if len(s) >= 19 else s, fmt[:len(fmt)])
            return (s, dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
        except (ValueError, TypeError):
            continue
    return None


async def create_event(name: str, description: str, start_at: str, end_at: str, rewards: list | None = None, status: str = "active") -> int:
    """Создаёт событие. rewards — список {place, description}. Валидирует даты. Возвращает id."""
    parsed_start = _parse_datetime(start_at)
    parsed_end = _parse_datetime(end_at)
    if not parsed_start or not parsed_end:
        raise ValueError("Invalid date format. Use YYYY-MM-DD HH:MM")
    _, start_iso = parsed_start
    _, end_iso = parsed_end
    if start_iso >= end_iso:
        raise ValueError("start_at must be before end_at")
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
            raise ValueError("Invalid start_at format. Use YYYY-MM-DD HH:MM")
        start_at = parsed[1]
    if end_at is not None:
        parsed = _parse_datetime(end_at)
        if not parsed:
            raise ValueError("Invalid end_at format. Use YYYY-MM-DD HH:MM")
        end_at = parsed[1]
    ev = await get_event_by_id(event_id)
    if not ev:
        return False
    # Проверка start < end при обновлении
    s = start_at if start_at is not None else ev.get("start_at")
    e = end_at if end_at is not None else ev.get("end_at")
    if s and e and s >= e:
        raise ValueError("start_at must be before end_at")
    return await db_update_event(event_id, name=name, description=description, start_at=start_at,
                                 end_at=end_at, rewards_json=rewards_json, status=status)


async def delete_event(event_id: int) -> bool:
    return await db_delete_event(event_id)
