"""
Выдача наград по итогам события: продление подписки топ-1/2/3 на N дней.
"""
import logging
import time
from bot.events.db.queries import (
    get_event_by_id,
    get_leaderboard_with_places,
    is_rewards_granted,
    set_rewards_granted,
)

logger = logging.getLogger(__name__)


async def grant_rewards(event_id: int) -> dict:
    """
    Начисляет награды по событию: для каждого места из rewards (place, days)
    находит рефереров с этим местом и продлевает им подписку на days дней.
    Возвращает { granted: bool, error?: str, extended: [{ user_id, subscription_id, days }] }.
    """
    ev = await get_event_by_id(event_id)
    if not ev:
        return {"granted": False, "error": "Event not found"}
    if await is_rewards_granted(event_id):
        return {"granted": False, "error": "Rewards already granted for this event"}
    rewards = ev.get("rewards") or []
    if not isinstance(rewards, list):
        rewards = []
    leaderboard = await get_leaderboard_with_places(event_id, limit=100)
    place_to_referrers = {}
    for row in leaderboard:
        p = row["place"]
        place_to_referrers.setdefault(p, []).append(row["referrer_user_id"])

    extended = []
    from bot.db.subscribers_db import get_all_active_subscriptions_by_user, update_subscription_expiry

    for r in rewards:
        place = r.get("place")
        days = int(r.get("days") or 0)
        if place is None or days <= 0:
            continue
        referrers = place_to_referrers.get(place, [])
        for user_id in referrers:
            subs = await get_all_active_subscriptions_by_user(user_id)
            if not subs:
                logger.warning("grant_rewards: no subscription for referrer user_id=%s", user_id)
                continue
            sub = max(subs, key=lambda s: s.get("expires_at") or 0)
            sub_id = sub.get("id")
            if not sub_id:
                continue
            current_expires = sub.get("expires_at") or int(time.time())
            new_expires = current_expires + days * 24 * 60 * 60
            try:
                await update_subscription_expiry(sub_id, new_expires)
                extended.append({"user_id": user_id, "subscription_id": sub_id, "days": days})
                logger.info("grant_rewards: extended subscription %s for user %s by %s days", sub_id, user_id, days)
            except Exception as e:
                logger.warning("grant_rewards: update_subscription_expiry failed for sub %s: %s", sub_id, e)

    await set_rewards_granted(event_id)
    return {"granted": True, "extended": extended}
