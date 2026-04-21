"""
Аутентификация и проверка прав для веб-API (Quart).
Используется из bot.web.routes.* через authenticate_request_async и check_admin_access_async.
"""
import logging

from ...utils.logging_helpers import log_event, mask_secret

logger = logging.getLogger(__name__)


AUTH_COOKIE_NAME = "daralla_web_token"


async def authenticate_request_async(headers, args, body, cookies=None):
    """
    Async auth for Quart. Call with:
      body = await request.get_json(silent=True) or {}
      user_id = await authenticate_request_async(request.headers, request.args, body, request.cookies)
    Поддерживает: Authorization Bearer, cookie daralla_web_token, initData (Telegram).
    """
    from ...db.users_db import get_user_by_auth_token, get_user_by_telegram_id_v2

    token = None
    web_token = headers.get("Authorization") if headers else None
    if web_token and web_token.startswith("Bearer "):
        token = web_token.split(" ", 1)[1]
    if not token and cookies:
        token = cookies.get(AUTH_COOKIE_NAME)
    if token:
        user = await get_user_by_auth_token(token)
        if user:
            log_event(
                logger,
                logging.INFO,
                "web_auth_success",
                user_id=user["user_id"],
            )
            return user["user_id"]
        log_event(
            logger,
            logging.WARNING,
            "web_auth_token_not_found",
            token=mask_secret(token),
        )

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
            log_event(logger, logging.ERROR, "telegram_initdata_missing_token")
            return None

        parsed_data = urllib.parse.parse_qs(init_data)

        if 'hash' not in parsed_data or not parsed_data['hash']:
            log_event(logger, logging.WARNING, "telegram_initdata_missing_hash")
            return None

        received_hash = parsed_data['hash'][0]

        if 'auth_date' not in parsed_data or not parsed_data['auth_date']:
            log_event(logger, logging.WARNING, "telegram_initdata_missing_auth_date")
            return None

        auth_date = int(parsed_data['auth_date'][0])
        current_time = int(time.time())
        if current_time - auth_date > 24 * 60 * 60:
            log_event(
                logger,
                logging.WARNING,
                "telegram_initdata_expired",
                auth_date=auth_date,
                current_time=current_time,
            )
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
            log_event(logger, logging.WARNING, "telegram_initdata_invalid_hash")
            return None

        if 'user' not in parsed_data or not parsed_data['user']:
            log_event(logger, logging.WARNING, "telegram_initdata_missing_user")
            return None

        user_data = json.loads(parsed_data['user'][0])
        user_id = str(user_data.get('id'))

        if not user_id:
            log_event(logger, logging.WARNING, "telegram_initdata_missing_user_id")
            return None

        log_event(
            logger,
            logging.INFO,
            "telegram_initdata_verified",
            user_id=user_id,
        )
        return user_id

    except Exception as e:
        log_event(
            logger,
            logging.ERROR,
            "telegram_initdata_verification_failed",
            error=str(e),
        )
        logger.debug("telegram_initdata_verification_failed_traceback", exc_info=True)
        return None


async def check_admin_access_async(user_id: str) -> bool:
    """
    Async-версия проверки прав админа для Quart.
    user_id в ADMIN_IDS или у пользователя telegram_id в ADMIN_IDS.
    """
    try:
        from ...app_context import get_ctx
        from ...db.users_db import get_user_by_id
        ctx = get_ctx()
        admin_set = {str(a) for a in ctx.admin_ids}

        user_id_str = str(user_id)
        if user_id_str in admin_set:
            log_event(logger, logging.INFO, "admin_access_granted_by_user_id", user_id=user_id)
            return True

        user = await get_user_by_id(user_id)
        if user:
            tid = user.get("telegram_id")
            if tid and str(tid) in admin_set:
                log_event(
                    logger,
                    logging.INFO,
                    "admin_access_granted_by_telegram_id",
                    user_id=user_id,
                    telegram_id=tid,
                )
                return True

        log_event(logger, logging.INFO, "admin_access_denied", user_id=user_id)
        return False
    except Exception as e:
        log_event(
            logger,
            logging.ERROR,
            "admin_access_check_failed",
            user_id=user_id,
            error=str(e),
        )
        logger.debug("admin_access_check_failed_traceback", exc_info=True)
        return False


def get_server_manager():
    """Возвращает server_manager из AppContext или None."""
    try:
        from ...app_context import get_ctx
        return get_ctx().server_manager
    except RuntimeError:
        return None


def get_subscription_manager():
    """Возвращает subscription_manager из AppContext или None."""
    try:
        from ...app_context import get_ctx
        return get_ctx().subscription_manager
    except RuntimeError:
        return None
