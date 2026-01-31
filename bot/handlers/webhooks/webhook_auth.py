"""
Общая аутентификация и проверка прав для webhook API.
"""
import asyncio
import logging
from flask import request

logger = logging.getLogger(__name__)


def authenticate_request():
    """Универсальная функция аутентификации (TG initData или Web Token)"""
    # 1. Проверяем заголовок Authorization (Web Token)
    web_token = request.headers.get('Authorization')
    if web_token and web_token.startswith('Bearer '):
        token = web_token.split(' ')[1]
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            from ...db.subscribers_db import get_user_by_auth_token
            user = loop.run_until_complete(get_user_by_auth_token(token))
            if user:
                logger.info(f"Успешная веб-аутентификация для user_id={user['user_id']}")
                return user['user_id']
            else:
                logger.warning(f"Веб-токен не найден в БД: {token[:10]}...")
        finally:
            loop.close()

    # 2. Проверяем initData (Telegram) - в URL или в теле JSON
    init_data = request.args.get('initData')
    if not init_data and request.is_json:
        try:
            data = request.get_json(silent=True)
            if data:
                init_data = data.get('initData')
        except Exception:
            pass

    if init_data:
        tg_user_id = verify_telegram_init_data(init_data)
        if not tg_user_id:
            return None
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            from ...db.subscribers_db import get_user_by_telegram_id_v2
            user = loop.run_until_complete(get_user_by_telegram_id_v2(tg_user_id, use_fallback=True))
            if user:
                return user['user_id']
            return None
        finally:
            loop.close()

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


def check_admin_access(user_id: str) -> bool:
    """Проверяет, является ли пользователь админом. Учитывает и user_id, и привязанный telegram_id."""
    try:
        from ... import bot as bot_module
        from ...db.subscribers_db import get_user_by_id
        ADMIN_IDS = getattr(bot_module, 'ADMIN_IDS', [])

        user_id_str = str(user_id)
        admin_set = {str(a) for a in ADMIN_IDS}

        if user_id_str in admin_set:
            logger.info(f"Пользователь {user_id} является админом (по user_id)")
            return True

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            user = loop.run_until_complete(get_user_by_id(user_id))
            if user:
                tid = user.get('telegram_id')
                if tid and str(tid) in admin_set:
                    logger.info(f"Пользователь {user_id} является админом (по telegram_id={tid})")
                    return True
        finally:
            loop.close()

        logger.info(f"Пользователь {user_id} НЕ является админом")
        return False
    except Exception as e:
        logger.error(f"Ошибка при проверке прав админа: {e}", exc_info=True)
        return False
