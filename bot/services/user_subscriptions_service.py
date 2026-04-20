"""Service wrappers for user subscription operations used by HTTP routes."""

from __future__ import annotations

from bot.db.subscriptions_db import (
    get_all_subscriptions_by_user,
    get_subscription_by_id,
    is_subscription_active,
    update_subscription_name,
)
from bot.db.users_db import get_user_server_usage


async def list_user_subscriptions(user_id: str):
    return await get_all_subscriptions_by_user(user_id)


def is_active_subscription(subscription: dict) -> bool:
    return is_subscription_active(subscription)


async def rename_subscription_for_user(sub_id: int, user_id: str, new_name: str) -> bool:
    sub = await get_subscription_by_id(sub_id, user_id)
    if not sub:
        return False
    await update_subscription_name(sub_id, new_name)
    return True


async def user_server_usage_map(user_id: str):
    return await get_user_server_usage(user_id)
