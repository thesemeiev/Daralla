"""Service helpers for /api/events route orchestration."""

from __future__ import annotations

import time

from bot.events.services import event_service
from bot.handlers.api_support.webhook_auth import authenticate_request_async, check_admin_access_async

_events_cache = None
_events_cache_ts = 0
_EVENTS_CACHE_TTL = 60


async def get_public_events_payload():
    global _events_cache, _events_cache_ts
    if _events_cache is not None and (time.time() - _events_cache_ts) < _EVENTS_CACHE_TTL:
        return _events_cache

    active = await event_service.list_active()
    upcoming = await event_service.list_upcoming()
    ended = await event_service.list_ended()
    payload = {"events": active + upcoming + ended, "active": active, "upcoming": upcoming, "ended": ended}
    _events_cache = payload
    _events_cache_ts = time.time()
    return payload


def invalidate_public_events_cache():
    global _events_cache, _events_cache_ts
    _events_cache = None
    _events_cache_ts = 0


async def require_admin_user(headers, args, body, cookies):
    user_id = await authenticate_request_async(headers, args, body, cookies)
    if not user_id:
        return None, 401
    if not await check_admin_access_async(user_id):
        return None, 403
    return user_id, None


async def require_authenticated_user(headers, args, body, cookies):
    user_id = await authenticate_request_async(headers, args, body, cookies)
    if not user_id:
        return None
    return user_id


async def get_user_referral_code(user_id: str):
    from bot.events.db.queries import get_or_create_referral_code

    return await get_or_create_referral_code(user_id)


async def get_event_leaderboard(event_id: int, limit: int):
    from bot.events.db.queries import get_leaderboard

    return await get_leaderboard(event_id, limit=limit)


async def get_event_my_place(event_id: int, user_id: str):
    from bot.events.db.queries import get_my_place

    return await get_my_place(event_id, user_id)
