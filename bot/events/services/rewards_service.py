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
    from bot.services.subscription_service import extend_subscription

    for r in rewards:
        place = r.get("place")
        days = int(r.get("days") or 0)
        if place is None or days <= 0:
            continue
        referrers = place_to_referrers.get(place, [])
        for user_id in referrers:
            account_id = int(user_id) if isinstance(user_id, str) and user_id.isdigit() else (int(user_id) if isinstance(user_id, int) else None)
            if account_id is None:
                logger.warning("grant_rewards: invalid referrer user_id=%s", user_id)
                continue
            try:
                new_expiry = await extend_subscription(account_id, days)
                if new_expiry:
                    extended.append({"user_id": user_id, "subscription_id": 0, "days": days})
                    logger.info("grant_rewards: extended subscription for account %s by %s days", account_id, days)
                else:
                    logger.warning("grant_rewards: extend failed for account_id=%s", account_id)
            except Exception as e:
                logger.warning("grant_rewards: extend_subscription failed for account %s: %s", account_id, e)

    await set_rewards_granted(event_id)
    return {"granted": True, "extended": extended}
