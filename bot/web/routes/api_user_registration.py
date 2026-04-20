"""Registration and onboarding handlers extracted from api_user routes."""

import time

from quart import jsonify, request

from bot.handlers.api_support.webhook_auth import verify_telegram_init_data
from bot.prices_config import get_default_device_limit_async
from bot.services.user_registration_service import (
    resolve_or_create_user_from_telegram_safe,
    subscription_group,
    touch_known_user,
    try_create_trial_subscription,
    user_profile_flags,
)
from bot.web.routes.admin_common import _cors_headers
from bot.web.routes.api_user_common import options_response_or_none, require_user_id


async def handle_api_user_register(_auth, logger):
    opt = options_response_or_none()
    if opt:
        return opt
    try:
        data = await request.get_json(silent=True) or {}
        user_id, _ = await require_user_id(_auth)
        init_data = request.args.get("initData") or data.get("initData")
        tg_user_id = verify_telegram_init_data(init_data) if init_data else None
        if not user_id and tg_user_id:
            user_id = None
        if not user_id and not tg_user_id:
            return jsonify({"error": "Invalid authentication"}), 401

        just_created_tg_user = False
        if not user_id and tg_user_id:
            _tg_str = str(tg_user_id)
            user_id, just_created_tg_user = await resolve_or_create_user_from_telegram_safe(_tg_str)
            if just_created_tg_user:
                logger.info(
                    "Регистрация нового TG-first пользователя: user_id=%s, telegram_id=%s",
                    user_id,
                    _tg_str,
                )
            else:
                logger.info(
                    "TG-first регистрация разрешена после гонки/существующей связи: telegram_id=%s, user_id=%s",
                    _tg_str,
                    user_id,
                )
        if not user_id:
            return jsonify({"error": "Invalid authentication"}), 401
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
                    from bot.app_context import get_ctx

                    _ctx = get_ctx()
                    subscription_manager = _ctx.subscription_manager
                    server_manager = _ctx.server_manager
                    if subscription_manager and server_manager:
                        group_id = await subscription_group(subscription_id)
                        servers_for_group = server_manager.get_servers_by_group(group_id)
                        unique_email = f"{user_id}_{subscription_id}"
                        all_configured_servers = [
                            s["name"] for s in servers_for_group if s.get("x3") is not None
                        ]
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

        return (
            jsonify(
                {
                    "success": True,
                    "was_new_user": not was_known_user,
                    "trial_created": trial_created,
                    "subscription_id": subscription_id,
                }
            ),
            200,
            _cors_headers(),
        )
    except Exception as e:
        logger.error("Ошибка регистрации пользователя: %s", e, exc_info=True)
        return jsonify({"error": "Internal server error"}), 500, _cors_headers()
