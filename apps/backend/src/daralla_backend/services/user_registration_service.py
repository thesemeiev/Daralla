"""Service helpers for user registration flow in api_user routes."""

from __future__ import annotations

import aiosqlite
import time

from daralla_backend.app_context import get_ctx
from daralla_backend.db import is_known_user, register_simple_user
from daralla_backend.db.subscriptions_db import (
    create_subscription,
    get_all_active_subscriptions_by_user,
    get_subscription_by_id_only,
    is_subscription_active,
)
from daralla_backend.db.users_db import (
    generate_user_id,
    get_or_create_subscriber,
    get_user_by_id,
    get_user_by_telegram_id_v2,
    is_known_telegram_id,
    mark_telegram_id_known,
    reconcile_users_telegram_id_with_link,
)
from daralla_backend.services.user_account_service import create_telegram_binding
from daralla_backend.prices_config import get_default_device_limit_async


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


async def register_user_with_trial(user_id: str | None, tg_user_id: str | None, logger):
    if not user_id and tg_user_id:
        user_id = None
    if not user_id and not tg_user_id:
        raise ValueError("Invalid authentication")

    just_created_tg_user = False
    if not user_id and tg_user_id:
        user_id, just_created_tg_user = await resolve_or_create_user_from_telegram_safe(str(tg_user_id))
        if just_created_tg_user:
            logger.info(
                "Регистрация нового TG-first пользователя: user_id=%s, telegram_id=%s",
                user_id,
                tg_user_id,
            )
        else:
            logger.info(
                "TG-first регистрация разрешена после гонки/существующей связи: telegram_id=%s, user_id=%s",
                tg_user_id,
                user_id,
            )
    if not user_id:
        raise ValueError("Invalid authentication")

    is_web, was_known_user = await user_profile_flags(
        user_id,
        str(tg_user_id) if tg_user_id else None,
        just_created_tg_user,
    )
    await touch_known_user(
        user_id,
        str(tg_user_id) if tg_user_id else None,
        just_created_tg_user,
    )

    trial_created = False
    subscription_id = None
    if not was_known_user and not is_web:
        try:
            now = int(time.time())
            trial_dl = await get_default_device_limit_async()
            logger.info("Создание пробной подписки для нового пользователя: %s", user_id)
            expires_at = now + (5 * 24 * 60 * 60)
            subscription_id, token = await try_create_trial_subscription(
                user_id=user_id,
                trial_device_limit=trial_dl,
                expires_at=expires_at,
            )
            if subscription_id:
                trial_created = True
                logger.info("Пробная подписка создана: subscription_id=%s", subscription_id)
                ctx = get_ctx()
                subscription_manager = ctx.subscription_manager
                server_manager = ctx.server_manager
                if subscription_manager and server_manager:
                    group_id = await subscription_group(subscription_id)
                    servers_for_group = server_manager.get_servers_by_group(group_id)
                    unique_email = f"{user_id}_{subscription_id}"
                    all_configured_servers = [s["name"] for s in servers_for_group if s.get("x3") is not None]
                    if all_configured_servers:
                        for server_name in all_configured_servers:
                            try:
                                await subscription_manager.attach_server_to_subscription(
                                    subscription_id=subscription_id,
                                    server_name=server_name,
                                    client_email=unique_email,
                                    client_id=None,
                                )
                            except Exception as attach_e:
                                if "UNIQUE constraint" not in str(attach_e) and "already exists" not in str(
                                    attach_e
                                ).lower():
                                    logger.error(
                                        "Ошибка привязки сервера %s: %s",
                                        server_name,
                                        attach_e,
                                    )
                        successful_servers = []
                        for server_name in all_configured_servers:
                            try:
                                client_exists, _ = await subscription_manager.ensure_client_on_server(
                                    subscription_id=subscription_id,
                                    server_name=server_name,
                                    client_email=unique_email,
                                    user_id=user_id,
                                    expires_at=expires_at,
                                    token=token,
                                    device_limit=trial_dl,
                                )
                                if client_exists:
                                    successful_servers.append(server_name)
                            except Exception as e:
                                logger.error("Ошибка создания клиента на %s: %s", server_name, e)
                        logger.info(
                            "Пробная подписка: создано на %s/%s серверах",
                            len(successful_servers),
                            len(all_configured_servers),
                        )
        except Exception as e:
            logger.error("Ошибка создания пробной подписки: %s", e, exc_info=True)

    return {
        "success": True,
        "was_new_user": not was_known_user,
        "trial_created": trial_created,
        "subscription_id": subscription_id,
    }
