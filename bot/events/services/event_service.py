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
    delete_event as db_delete_event,
)

logger = logging.getLogger(__name__)


async def create_event(name: str, description: str, start_at: str, end_at: str, rewards: list | None = None, status: str = "active") -> int:
    """Создаёт событие. rewards — список {place, days}. Возвращает id."""
    rewards_json = json.dumps(rewards or [])
    return await db_create_event(name, description, start_at, end_at, rewards_json=rewards_json, status=status)


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


async def delete_event(event_id: int) -> bool:
    return await db_delete_event(event_id)
