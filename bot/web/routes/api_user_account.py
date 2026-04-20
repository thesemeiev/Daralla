"""Account/auth-related handlers extracted from api_user routes."""

import os

import requests as requests_lib
from quart import Response, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from bot.handlers.api_support.webhook_auth import verify_telegram_init_data
from bot.services.user_account_service import (
    convert_legacy_user_to_web,
    create_link_state_for_user,
    fetch_user_by_id,
    fetch_user_by_telegram_id,
    get_notification_chat_id,
    is_username_available_for_user,
    unlink_telegram_id,
    update_password,
    update_user_credentials,
    update_username,
)
from bot.web.auth_validation import validate_password_format, validate_username_format
from bot.web.routes.api_user_common import options_response_or_none, require_user_id


async def handle_api_user_web_access_setup(logger):
    opt = options_response_or_none()
    if opt:
        return opt
    try:
        data = await request.get_json(silent=True) or {}
        init_data = data.get("initData")
        if not init_data:
            return jsonify({"error": "Telegram data required"}), 400
        telegram_id = verify_telegram_init_data(init_data)
        if not telegram_id:
            return jsonify({"error": "Invalid authentication"}), 401
        username = (data.get("username") or "").strip().lower()
        password = (data.get("password") or "").strip()
        ok, err = validate_username_format(username)
        if not ok:
            return jsonify({"error": err}), 400
        ok, err = validate_password_format(password)
        if not ok:
            return jsonify({"error": err}), 400
        user = await fetch_user_by_telegram_id(str(telegram_id))
        if not user:
            return jsonify({"error": "Пользователь не найден"}), 404
        user_id = user["user_id"]
        ok = await is_username_available_for_user(username, user_id)
        if not ok:
            return jsonify({"error": "Этот логин уже занят"}), 409
        password_hash = generate_password_hash(password)
        await update_user_credentials(user_id, username, password_hash)
        return jsonify(
            {
                "success": True,
                "message": f"Web-доступ настроен. Теперь вы можете войти на сайт с логином {username}.",
                "username": username,
            }
        )
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
        if not token:
            return Response(status=500)
        user = await fetch_user_by_id(user_id)
        if not user:
            return Response(status=404)
        tid = user.get("telegram_id")
        if not tid:
            return Response(status=404)
        base = f"https://api.telegram.org/bot{token}"
        photos_r = requests_lib.get(
            f"{base}/getUserProfilePhotos",
            params={"user_id": int(tid), "limit": 1},
            timeout=10,
        )
        if not photos_r.ok:
            logger.warning("getUserProfilePhotos: %s %s", photos_r.status_code, photos_r.text[:200])
            return Response(status=502)
        data = photos_r.json()
        if not data.get("ok") or not data.get("result", {}).get("photos"):
            return Response(status=404)
        file_id = data["result"]["photos"][0][-1]["file_id"]
        file_r = requests_lib.get(f"{base}/getFile", params={"file_id": file_id}, timeout=10)
        if not file_r.ok:
            logger.warning("getFile: %s %s", file_r.status_code, file_r.text[:200])
            return Response(status=502)
        file_data = file_r.json()
        if not file_data.get("ok"):
            return Response(status=404)
        file_path = file_data["result"].get("file_path")
        if not file_path:
            return Response(status=404)
        r = requests_lib.get(f"https://api.telegram.org/file/bot{token}/{file_path}", timeout=10)
        if not r.ok:
            return Response(status=502)
        return Response(
            r.content,
            mimetype="image/jpeg",
            headers={"Cache-Control": "private, max-age=3600"},
        )
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
        user = await fetch_user_by_id(user_id)
        if not user or not user.get("password_hash"):
            return jsonify({"error": "Пароль для этого аккаунта не настроен"}), 400
        if not check_password_hash(user["password_hash"], current):
            return jsonify({"error": "Неверный текущий пароль"}), 401
        if check_password_hash(user["password_hash"], new_pw):
            return jsonify({"error": "Новый пароль должен отличаться от текущего"}), 400
        new_hash = generate_password_hash(new_pw)
        await update_password(user_id, new_hash)
        return jsonify({"success": True, "message": "Пароль изменён"})
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
        user = await fetch_user_by_id(user_id)
        if not user or not user.get("password_hash"):
            return jsonify({"error": "Пароль для этого аккаунта не настроен"}), 400
        if not check_password_hash(user["password_hash"], current):
            return jsonify({"error": "Неверный текущий пароль"}), 401
        cur_username = (user.get("username") or "").strip().lower()
        if new_login == cur_username:
            return jsonify({"error": "Укажите новый логин, отличный от текущего"}), 400
        ok = await is_username_available_for_user(new_login, user_id)
        if not ok:
            return jsonify({"error": "Этот логин уже занят"}), 409
        await update_username(user_id, new_login)
        return jsonify({"success": True, "message": "Логин изменён", "username": new_login})
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
        user = await fetch_user_by_id(user_id)
        if not user:
            return jsonify({"error": "Пользователь не найден"}), 404
        if not user.get("password_hash"):
            return jsonify({"error": "Для отвязки Telegram необходимо сначала настроить веб-доступ (логин и пароль)"}), 400
        if not check_password_hash(user["password_hash"], current_password):
            return jsonify({"error": "Неверный текущий пароль"}), 401
        telegram_id = user.get("telegram_id")
        if telegram_id is not None:
            telegram_id = str(telegram_id)
        if not telegram_id:
            _chat_id = await get_notification_chat_id(user_id)
            if _chat_id is not None:
                telegram_id = str(_chat_id)
        is_legacy_tg_format = user_id.startswith("tg_") or user_id.isdigit()
        if not telegram_id:
            return jsonify({"error": "Telegram не привязан к этому аккаунту"}), 400
        if is_legacy_tg_format:
            username = user.get("username")
            if not username:
                return jsonify({"error": "Ошибка: у аккаунта нет логина для превращения в веб-аккаунт. Сначала смените логин."}), 400
            new_user_id = await convert_legacy_user_to_web(user_id, username)
            logger.info("Аккаунт %s превращен в %s при отвязке TG", user_id, new_user_id)
            user_id = new_user_id
        await unlink_telegram_id(user_id, telegram_id)
        logger.info("Отвязан Telegram %s от аккаунта %s. Связь в telegram_links удалена.", telegram_id, user_id)
        return jsonify(
            {
                "success": True,
                "message": "Telegram успешно отвязан. Аккаунт переведен в режим веб-доступа.",
            }
        )
    except Exception as e:
        logger.error("Ошибка unlink-telegram: %s", e, exc_info=True)
        return jsonify({"error": str(e)}), 500
