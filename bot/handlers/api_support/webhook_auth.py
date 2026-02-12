"""
Аутентификация и проверка прав для веб-API (Quart).
Используется из bot.web.routes.* через authenticate_request_async и check_admin_access_async.
"""
import logging

logger = logging.getLogger(__name__)


async def authenticate_request_async(headers, args, body):
    """
    Async auth for Quart. Call with:
      body = await request.get_json(silent=True) or {}
      user_id = await authenticate_request_async(request.headers, request.args, body)
    """
    from ...db.users_db import get_user_by_auth_token, get_user_by_telegram_id_v2

    web_token = headers.get("Authorization") if headers else None
    if web_token and web_token.startswith("Bearer "):
        token = web_token.split(" ")[1]
        user = await get_user_by_auth_token(token)
        if user:
            logger.info("Успешная веб-аутентификация для user_id=%s", user["user_id"])
            return user["user_id"]
        logger.warning("Веб-токен не найден в БД: %s...", token[:10])

    init_data = (args.get("initData") if args else None) or (body.get("initData") if body else None)
    if init_data:
        tg_user_id = verify_telegram_init_data(init_data)
        if tg_user_id:
            user = await get_user_by_telegram_id_v2(str(tg_user_id), use_fallback=True)
            if user:
                return user["user_id"]
    return None


def verify_telegram_init_data(init_data: str):
    """
    Проверяет initData от Telegram Web App и возвращает user_id если валидно.

    Args:
        init_data: Строка initData от Telegram (формат: hash=...&user=...&auth_date=...)

    Returns:
        user_id: ID пользователя Telegram, или None если данные невалидны
    """
    try:
        import os
        import hmac
        import hashlib
        import urllib.parse
        import json
        import time

        TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
        if not TELEGRAM_TOKEN:
            logger.error("TELEGRAM_TOKEN не найден")
            return None

        parsed_data = urllib.parse.parse_qs(init_data)

        if 'hash' not in parsed_data or not parsed_data['hash']:
            logger.warning("Hash не найден в initData")
            return None

        received_hash = parsed_data['hash'][0]

        if 'auth_date' not in parsed_data or not parsed_data['auth_date']:
            logger.warning("auth_date не найден в initData")
            return None

        auth_date = int(parsed_data['auth_date'][0])
        current_time = int(time.time())
        if current_time - auth_date > 24 * 60 * 60:
            logger.warning(f"initData устарел: auth_date={auth_date}, current={current_time}")
            return None

        secret_key = hmac.new(
            b"WebAppData",
            TELEGRAM_TOKEN.encode('utf-8'),
            hashlib.sha256
        ).digest()

        data_check_string_parts = []
        for key in sorted(parsed_data.keys()):
            if key != 'hash':
                data_check_string_parts.append(f"{key}={parsed_data[key][0]}")

        data_check_string = "\n".join(data_check_string_parts)
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        if calculated_hash != received_hash:
            logger.warning("Неверный hash в initData")
            return None

        if 'user' not in parsed_data or not parsed_data['user']:
            logger.warning("user не найден в initData")
            return None

        user_data = json.loads(parsed_data['user'][0])
        user_id = str(user_data.get('id'))

        if not user_id:
            logger.warning("user_id не найден в user данных")
            return None

        logger.info(f"Успешная проверка initData для user_id={user_id}")
        return user_id

    except Exception as e:
        logger.error(f"Ошибка при проверке initData: {e}", exc_info=True)
        return None


async def check_admin_access_async(user_id: str) -> bool:
    """
    Async-версия проверки прав админа для Quart. Та же логика, что check_admin_access:
    user_id в ADMIN_IDS или у пользователя telegram_id в ADMIN_IDS.
    """
    try:
        from ... import bot as bot_module
        from ...db.users_db import get_user_by_id
        ADMIN_IDS = getattr(bot_module, "ADMIN_IDS", [])

        user_id_str = str(user_id)
        admin_set = {str(a) for a in ADMIN_IDS}

        if user_id_str in admin_set:
            logger.info("Пользователь %s является админом (по user_id)", user_id)
            return True

        user = await get_user_by_id(user_id)
        if user:
            tid = user.get("telegram_id")
            if tid and str(tid) in admin_set:
                logger.info("Пользователь %s является админом (по telegram_id=%s)", user_id, tid)
                return True

        logger.info("Пользователь %s НЕ является админом", user_id)
        return False
    except Exception as e:
        logger.error("Ошибка при проверке прав админа: %s", e, exc_info=True)
        return False


def get_bot_module():
    """Возвращает модуль bot.bot для доступа к глобальным объектам (server_manager, subscription_manager и т.д.)."""
    try:
        import sys
        bot_module = sys.modules.get('bot.bot')
        if bot_module is not None:
            return bot_module
        from ... import bot as bot_module
        return bot_module
    except (ImportError, AttributeError):
        return None


def get_server_manager():
    """Возвращает server_manager из bot.bot или None."""
    bot_module = get_bot_module()
    return getattr(bot_module, 'server_manager', None) if bot_module else None


def get_subscription_manager():
    """Возвращает subscription_manager из bot.bot или None."""
    bot_module = get_bot_module()
    return getattr(bot_module, 'subscription_manager', None) if bot_module else None
