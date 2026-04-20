"""Service helpers for user registration flow in api_user routes."""

from __future__ import annotations

import aiosqlite

from bot.db import is_known_user, register_simple_user
from bot.db.subscriptions_db import (
    create_subscription,
    get_all_active_subscriptions_by_user,
    get_subscription_by_id_only,
    is_subscription_active,
)
from bot.db.users_db import (
    generate_user_id,
    get_or_create_subscriber,
    get_user_by_id,
    get_user_by_telegram_id_v2,
    is_known_telegram_id,
    mark_telegram_id_known,
    reconcile_users_telegram_id_with_link,
)
from bot.services.user_account_service import create_telegram_binding


async def resolve_or_create_user_from_telegram(telegram_id: str):
    existing = await get_user_by_telegram_id_v2(telegram_id, use_fallback=True)
    if existing:
        return existing["user_id"], False

    user_id = generate_user_id()
    await register_simple_user(user_id)
    await create_telegram_binding(telegram_id, user_id)
    return user_id, True


async def resolve_or_create_user_from_telegram_safe(telegram_id: str):
    """
    Resolve/create TG-first user with race-safe recovery.
    """
    try:
        return await resolve_or_create_user_from_telegram(telegram_id)
    except aiosqlite.IntegrityError:
        recovered = await recover_user_after_integrity_conflict(telegram_id)
        if not recovered:
            raise
        return recovered, False


async def recover_user_after_integrity_conflict(telegram_id: str):
    await reconcile_users_telegram_id_with_link(telegram_id)
    existing = await get_user_by_telegram_id_v2(telegram_id, use_fallback=True)
    return existing["user_id"] if existing else None


async def user_profile_flags(user_id: str, telegram_id: str | None, just_created_tg_user: bool):
    user = await get_user_by_id(user_id)
    is_web = bool(user.get("is_web", 0)) if user else False
    was_known_user = await is_known_user(user_id)
    if telegram_id:
        was_known_user = was_known_user or await is_known_telegram_id(telegram_id)
    if just_created_tg_user:
        was_known_user = False
    return is_web, was_known_user


async def touch_known_user(user_id: str, telegram_id: str | None, just_created_tg_user: bool):
    if not just_created_tg_user:
        await register_simple_user(user_id)
    if telegram_id:
        await mark_telegram_id_known(telegram_id)


async def try_create_trial_subscription(user_id: str, trial_device_limit: int, expires_at: int):
    existing_subs = await get_all_active_subscriptions_by_user(user_id)
    active_subs = [s for s in existing_subs if is_subscription_active(s)]
    if active_subs:
        return None, None

    subscriber_id = await get_or_create_subscriber(user_id)
    subscription_id, token = await create_subscription(
        subscriber_id=subscriber_id,
        period="month",
        device_limit=trial_device_limit,
        price=0.0,
        expires_at=expires_at,
        name="Пробная подписка",
    )
    return subscription_id, token


async def subscription_group(subscription_id: int):
    sub = await get_subscription_by_id_only(subscription_id)
    return sub.get("group_id") if sub else None
