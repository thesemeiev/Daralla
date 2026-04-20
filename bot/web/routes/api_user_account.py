"""Account/auth-related handlers extracted from api_user routes."""

import os

from quart import Response, jsonify, request

from bot.services.user_account_service import (
    UserAccountServiceError,
    UserAvatarServiceError,
    change_login_for_user,
    change_password_for_user,
    create_link_state_for_user,
    fetch_user_by_id,
    load_user_avatar_bytes,
    setup_web_access_for_telegram_user,
    unlink_telegram_for_user,
)
from bot.web.auth_validation import validate_password_format, validate_username_format
from bot.web.routes.api_user_common import options_response_or_none, require_user_id
from bot.web.routes.transport import error_response, service_error_response


async def handle_api_user_web_access_setup(logger):
    opt = options_response_or_none()
    if opt:
        return opt
    try:
        data = await request.get_json(silent=True) or {}
        init_data = data.get("initData")
        if not init_data:
            return error_response("Telegram data required", 400)
        username = (data.get("username") or "").strip().lower()
        password = (data.get("password") or "").strip()
        ok, err = validate_username_format(username)
        if not ok:
            return jsonify({"error": err}), 400
        ok, err = validate_password_format(password)
        if not ok:
            return jsonify({"error": err}), 400
        result = await setup_web_access_for_telegram_user(init_data, username, password)
        return jsonify(
            {
                "success": True,
                "message": f"Web-доступ настроен. Теперь вы можете войти на сайт с логином {username}.",
                "username": result["username"],
            }
        )
    except UserAccountServiceError as e:
        return service_error_response(e)
    except Exception as e:
        logger.error("Ошибка web-access/setup: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


async def handle_api_user_link_telegram_start(_auth, logger):
    opt = options_response_or_none()
    if opt:
        return opt
    try:
        user_id, err = await require_user_id(_auth, "Требуется авторизация")
        if err:
            return jsonify(err[0]), err[1]

        user = await fetch_user_by_id(user_id)
        if not user:
            return jsonify({"error": "Пользователь не найден"}), 404
        if user.get("telegram_id"):
            return jsonify({"error": "Telegram уже привязан"}), 400
        state = await create_link_state_for_user(user_id)
        bot_username = os.getenv("BOT_USERNAME", "Daralla_bot").strip()
        link = f"https://t.me/{bot_username}?start=link_{state}"
        return jsonify({"success": True, "link": link, "state": state})
    except Exception as e:
        logger.error("Ошибка link-telegram/start: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


async def handle_api_user_link_status(_auth, logger):
    opt = options_response_or_none()
    if opt:
        return opt
    try:
        user_id, err = await require_user_id(_auth, "Требуется авторизация")
        if err:
            return jsonify(err[0]), err[1]

        user = await fetch_user_by_id(user_id)
        if not user:
            return jsonify({"error": "Пользователь не найден"}), 404
        uid = user.get("user_id")
        tid = user.get("telegram_id")
        is_web = bool(user.get("is_web", 0))
        is_tg_first = not is_web
        telegram_linked = is_tg_first or (is_web and bool(tid))
        display_tid = tid or (uid if (uid and uid.isdigit()) else None)
        username = (user.get("username") or "").strip() or None
        web_access_enabled = bool(user.get("password_hash"))
        return jsonify(
            {
                "success": True,
                "telegram_linked": telegram_linked,
                "is_web": is_web,
                "username": username,
                "user_id": uid,
                "telegram_id": display_tid,
                "web_access_enabled": web_access_enabled,
            }
        )
    except Exception as e:
        logger.error("Ошибка link-status: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


async def handle_api_user_avatar(_auth, logger):
    opt = options_response_or_none()
    if opt:
        return opt
    try:
        user_id, err = await require_user_id(_auth, "Invalid authentication")
        if err:
            return Response(status=401)
        token = os.getenv("TELEGRAM_TOKEN")
        avatar_bytes = await load_user_avatar_bytes(user_id, token)
        return Response(
            avatar_bytes,
            mimetype="image/jpeg",
            headers={"Cache-Control": "private, max-age=3600"},
        )
    except UserAvatarServiceError as e:
        return Response(status=e.status_code)
    except Exception as e:
        logger.error("Ошибка /api/user/avatar: %s", e, exc_info=True)
        return Response(status=500)


async def handle_api_user_change_password(_auth, logger):
    opt = options_response_or_none()
    if opt:
        return opt
    try:
        user_id, err = await require_user_id(_auth, "Требуется авторизация")
        if err:
            return jsonify(err[0]), err[1]
        data = await request.get_json(silent=True) or {}
        current = (data.get("current_password") or "").strip()
        new_pw = (data.get("new_password") or "").strip()
        if not current:
            return jsonify({"error": "Введите текущий пароль"}), 400
        ok, err = validate_password_format(new_pw)
        if not ok:
            return jsonify({"error": err}), 400
        await change_password_for_user(user_id, current, new_pw)
        return jsonify({"success": True, "message": "Пароль изменён"})
    except UserAccountServiceError as e:
        return service_error_response(e)
    except Exception as e:
        logger.error("Ошибка change-password: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


async def handle_api_user_change_login(_auth, logger):
    opt = options_response_or_none()
    if opt:
        return opt
    try:
        user_id, err = await require_user_id(_auth, "Требуется авторизация")
        if err:
            return jsonify(err[0]), err[1]
        data = await request.get_json(silent=True) or {}
        current = (data.get("current_password") or "").strip()
        new_login = (data.get("new_login") or "").strip().lower()
        if not current:
            return jsonify({"error": "Введите текущий пароль"}), 400
        ok, err = validate_username_format(new_login)
        if not ok:
            return jsonify({"error": err}), 400
        await change_login_for_user(user_id, current, new_login)
        return jsonify({"success": True, "message": "Логин изменён", "username": new_login})
    except UserAccountServiceError as e:
        return service_error_response(e)
    except Exception as e:
        logger.error("Ошибка change-login: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500


async def handle_api_user_unlink_telegram(_auth, logger):
    opt = options_response_or_none()
    if opt:
        return opt
    try:
        user_id, err = await require_user_id(_auth, "Требуется авторизация")
        if err:
            return jsonify(err[0]), err[1]
        data = await request.get_json(silent=True) or {}
        current_password = (data.get("current_password") or "").strip()
        if not current_password:
            return jsonify({"error": "Введите текущий пароль"}), 400
        result = await unlink_telegram_for_user(user_id, current_password)
        logger.info(
            "Отвязан Telegram %s от аккаунта %s. Связь в telegram_links удалена.",
            result["telegram_id"],
            result["user_id"],
        )
        return jsonify(
            {
                "success": True,
                "message": "Telegram успешно отвязан. Аккаунт переведен в режим веб-доступа.",
            }
        )
    except UserAccountServiceError as e:
        return service_error_response(e)
    except Exception as e:
        logger.error("Ошибка unlink-telegram: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500
