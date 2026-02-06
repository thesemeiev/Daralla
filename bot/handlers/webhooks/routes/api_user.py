"""
Blueprint: /api/user/* and /api/subscriptions.
"""
import datetime
import logging
import os
import secrets
import time
import uuid
from flask import Blueprint, request, Response
from werkzeug.security import generate_password_hash, check_password_hash
import requests as requests_lib

from ..webhook_utils import require_auth, APIResponse, run_async, AuthContext, handle_options

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint('api_user', __name__)

    @bp.route('/api/user/register', methods=['POST', 'OPTIONS'])
    @require_auth
    def api_user_register(auth: AuthContext):
        """Регистрация/приветствие при первом открытии мини-приложения. Работает по account_id."""
        if request.method == 'OPTIONS':
            return handle_options()
        try:
            async def fetch_data():
                from ....db.accounts_db import get_remnawave_mapping, set_remnawave_mapping
                mapping = await get_remnawave_mapping(auth.account_id)
                was_new_user = mapping is None
                short_uuid = mapping.get("remnawave_short_uuid") if mapping else None

                try:
                    from ....services.remnawave_service import load_remnawave_config, RemnawaveClient
                    from ....db.accounts_db import get_telegram_id_for_account
                    cfg = load_remnawave_config()
                    client = RemnawaveClient(cfg)
                    telegram_id = await get_telegram_id_for_account(auth.account_id)
                    if mapping:
                        short_uuid = short_uuid or (mapping.get("remnawave_short_uuid"))
                    else:
                        remna_user = await client.get_user_by_telegram_id(telegram_id) if telegram_id else None
                        if remna_user:
                            short_uuid = remna_user.get("shortUuid") or remna_user.get("short_uuid")
                            await set_remnawave_mapping(
                                auth.account_id,
                                remna_user.get("uuid", remna_user.get("id", "")),
                                short_uuid,
                            )
                        elif telegram_id:
                            import datetime as dt
                            trial_days = 5
                            expire_at = dt.datetime.utcnow() + dt.timedelta(days=trial_days)
                            expire_at_iso = expire_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                            create_payload = {
                                "telegramId": int(telegram_id),
                                "username": f"acc_{auth.account_id}",
                                "expireAt": expire_at_iso,
                            }
                            created = await client.create_user(create_payload)
                            ruuid = created.get("uuid") or created.get("id") or created.get("obj", {}).get("uuid")
                            short_uuid = created.get("shortUuid") or created.get("short_uuid") or (created.get("obj", {}) or {}).get("shortUuid")
                            if ruuid:
                                await set_remnawave_mapping(auth.account_id, str(ruuid), short_uuid)
                except Exception as remna_e:
                    logger.warning("Remnawave create/lookup skipped: %s", remna_e)

                return APIResponse.success(
                    was_new_user=was_new_user,
                    account_id=auth.account_id,
                    short_uuid=short_uuid,
                )

            return run_async(fetch_data())
        except Exception as e:
            logger.error("Ошибка регистрации пользователя: %s", e, exc_info=True)
            return APIResponse.internal_error()

    @bp.route('/api/subscriptions', methods=['GET', 'OPTIONS'])
    @require_auth
    def api_subscriptions(auth: AuthContext):
        """Подписки пользователя из Remnawave (source of truth)."""
        if request.method == 'OPTIONS':
            return handle_options()
        try:
            async def fetch_subs():
                from ....services.subscription_service import get_subscriptions_for_account
                formatted_subs = await get_subscriptions_for_account(auth.account_id)
                return APIResponse.success(
                    subscriptions=formatted_subs,
                    total=len(formatted_subs),
                    active=len([s for s in formatted_subs if s['status'] == 'active'])
                )
            return run_async(fetch_subs())
        except Exception as e:
            logger.error("Ошибка в API /api/subscriptions: %s", e, exc_info=True)
            return APIResponse.internal_error()

    @bp.route('/api/user/payment/create', methods=['POST', 'OPTIONS'])
    @require_auth
    def api_user_payment_create(auth: AuthContext):
        """API endpoint для создания платежа (покупка или продление подписки). В БД хранится account_id."""
        if request.method == 'OPTIONS':
            return handle_options()
        try:
            data = request.get_json(silent=True) or {}
            period = data.get('period')
            subscription_id = data.get('subscription_id')
            if not period or period not in ['month', '3month']:
                return APIResponse.bad_request('Invalid period. Use "month" or "3month"')
            from ....prices_config import PRICES
            price = f"{PRICES[period]:.2f}"
            from yookassa import Payment
            from ....db import add_payment, PAYMENTS_DB_PATH
            import aiosqlite

            async def create_payment():
                async def cancel_old_payments():
                    async with aiosqlite.connect(PAYMENTS_DB_PATH) as db:
                        await db.execute(
                            'UPDATE payments SET status = ? WHERE account_id = ? AND status = ?',
                            ('canceled', str(auth.account_id), 'pending')
                        )
                        await db.commit()
                await cancel_old_payments()
                now = int(datetime.datetime.now().timestamp())
                subscription_uuid = str(uuid.uuid4())
                unique_email = f'{auth.account_id}_{subscription_uuid}'
                payment_period = f"extend_sub_{period}" if subscription_id else period
                payment = Payment.create({
                    "amount": {"value": price, "currency": "RUB"},
                    "confirmation": {"type": "redirect", "return_url": "https://t.me/"},
                    "capture": True,
                    "description": f"VPN {period}",
                    "metadata": {
                        "account_id": auth.account_id,
                        "type": payment_period,
                        "device_limit": 1,
                        "unique_email": unique_email,
                        "price": price,
                    },
                    "receipt": {
                        "customer": {"email": f"{auth.account_id}@vpn.local"},
                        "items": [{
                            "description": f"VPN {period}",
                            "quantity": "1.00",
                            "amount": {"value": price, "currency": "RUB"},
                            "vat_code": 1
                        }]
                    }
                })
                payment_meta = {
                    "price": price,
                    "type": payment_period,
                    "unique_email": unique_email,
                    "message_id": None
                }
                if subscription_id:
                    payment_meta['extension_subscription_id'] = int(subscription_id)
                
                if not payment.id:
                    return APIResponse.error("Failed to create payment", 500)
                
                await add_payment(
                    payment_id=payment.id,
                    account_id=auth.account_id,
                    status='pending',
                    meta=payment_meta
                )
                
                confirmation_url = None
                if payment.confirmation:
                    confirmation_url = payment.confirmation.confirmation_url
                
                if not confirmation_url:
                    return APIResponse.error("Failed to get payment confirmation URL", 500)
                
                return APIResponse.success(
                    payment_id=payment.id,
                    payment_url=confirmation_url,
                    amount=price,
                    period=period
                )

            return run_async(create_payment())
        except Exception as e:
            logger.error(f"Ошибка в API /api/user/payment/create: {e}", exc_info=True)
            return APIResponse.internal_error()

    @bp.route('/api/user/payment/status/<payment_id>', methods=['GET', 'OPTIONS'])
    @require_auth
    def api_user_payment_status(auth: AuthContext, payment_id):
        """API endpoint для проверки статуса платежа"""
        if request.method == 'OPTIONS':
            return handle_options()
        try:
            async def fetch_status():
                from ....db import get_payment_by_id
                payment_info = await get_payment_by_id(payment_id)
                if not payment_info:
                    return APIResponse.not_found("Payment not found")
                if payment_info.get('account_id') != str(auth.account_id):
                    return APIResponse.forbidden("Access denied")
                payload = {
                    'payment_id': payment_id,
                    'status': payment_info['status'],
                    'activated': bool(payment_info.get('activated', 0))
                }
                if payment_info['status'] == 'succeeded' and payment_info.get('meta'):
                    meta = payment_info['meta'] if isinstance(payment_info['meta'], dict) else {}
                    if meta.get('subscription_url'):
                        payload['subscription_url'] = meta['subscription_url']
                    if meta.get('expires_at'):
                        payload['expires_at'] = int(meta['expires_at'])
                    if meta.get('period'):
                        payload['period'] = meta['period']
                    if meta.get('device_limit') is not None:
                        payload['device_limit'] = int(meta['device_limit'])
                return APIResponse.success(**payload)

            result = run_async(fetch_status())
            if isinstance(result, tuple) and len(result) == 3:
                return result
            return result
        except Exception as e:
            logger.error(f"Ошибка в API /api/user/payment/status/{payment_id}: {e}", exc_info=True)
            return APIResponse.internal_error()

    @bp.route('/api/user/server-usage', methods=['GET', 'OPTIONS'])
    @require_auth
    def api_user_server_usage(auth: AuthContext):
        """Данные о серверах из Remnawave (ноды для карты и списка)."""
        if request.method == 'OPTIONS':
            return handle_options()
        try:
            async def fetch_servers():
                from ....services.remnawave_service import is_remnawave_configured
                from ....services.nodes_display_service import get_remnawave_nodes_for_display

                if is_remnawave_configured():
                    servers_info = await get_remnawave_nodes_for_display()
                else:
                    servers_info = []
                return APIResponse.success(servers=servers_info)

            return run_async(fetch_servers())
        except Exception as e:
            logger.error(f"Ошибка в API /api/user/server-usage: {e}", exc_info=True)
            return APIResponse.internal_error()

    @bp.route('/api/user/web-access/setup', methods=['POST', 'OPTIONS'])
    def api_user_web_access_setup():
        """Настройка web-доступа из Mini App (логин + пароль)"""
        if request.method == 'OPTIONS':
            return handle_options()
        try:
            from ..webhook_auth import verify_telegram_init_data
            data = request.get_json(silent=True) or {}
            init_data = data.get('initData')
            if not init_data:
                return APIResponse.bad_request('Telegram data required')
            telegram_id = verify_telegram_init_data(init_data)
            if not telegram_id:
                return APIResponse.unauthorized('Invalid authentication')
            username = (data.get('username') or '').strip().lower()
            password = (data.get('password') or '').strip()
            if len(username) < 3:
                return APIResponse.bad_request('Логин слишком короткий (мин. 3 символа)')
            if len(password) < 6:
                return APIResponse.bad_request('Пароль слишком короткий (мин. 6 символов)')
            from ....db.accounts_db import (
                get_or_create_account_for_telegram,
                replace_password_identity,
                set_account_password,
                username_available,
            )
            password_hash = generate_password_hash(password)

            async def setup():
                account_id = await get_or_create_account_for_telegram(telegram_id)
                ok = await username_available(username, exclude_account_id=None)
                if not ok:
                    return APIResponse.conflict('Этот логин уже занят')
                await replace_password_identity(account_id, username)
                await set_account_password(account_id, password_hash)
                return APIResponse.success(
                    message=f'Web-доступ настроен. Теперь вы можете войти на сайт с логином {username}.',
                    username=username,
                    account_id=account_id,
                )

            return run_async(setup())
        except Exception as e:
            logger.error(f"Ошибка web-access/setup: {e}", exc_info=True)
            return APIResponse.internal_error()

    @bp.route('/api/user/link-telegram/start', methods=['POST', 'OPTIONS'])
    @require_auth
    def api_user_link_telegram_start(auth: AuthContext):
        """Начать привязку Telegram. В state сохраняем str(account_id)."""
        if request.method == 'OPTIONS':
            return handle_options()
        try:
            async def start_link():
                from ....db.accounts_db import get_telegram_id_for_account, link_telegram_create_state
                tid = await get_telegram_id_for_account(auth.account_id)
                if tid:
                    return APIResponse.bad_request('Telegram уже привязан')
                state = await link_telegram_create_state(auth.account_id)
                bot_username = os.getenv('BOT_USERNAME', 'Daralla_bot')
                link = f"https://t.me/{bot_username}?start=link_{state}"
                return APIResponse.success(link=link, state=state)

            return run_async(start_link())
        except Exception as e:
            logger.error("Ошибка link-telegram/start: %s", e, exc_info=True)
            return APIResponse.internal_error()

    @bp.route('/api/user/link-status', methods=['GET', 'OPTIONS'])
    @require_auth
    def api_user_link_status(auth: AuthContext):
        """Статус привязки Telegram и веб-доступа по account_id и identities."""
        if request.method == 'OPTIONS':
            return handle_options()
        try:
            async def fetch_status():
                from ....db.accounts_db import (
                    get_telegram_id_for_account,
                    get_username_for_account,
                    get_remnawave_mapping,
                    get_account_password_hash,
                )
                tid = await get_telegram_id_for_account(auth.account_id)
                username = await get_username_for_account(auth.account_id)
                mapping = await get_remnawave_mapping(auth.account_id)
                short_uuid = mapping.get("remnawave_short_uuid") if mapping else None
                pwd_hash = await get_account_password_hash(auth.account_id)
                web_access_enabled = pwd_hash is not None
                from ....config import SUBSCRIPTION_URL, WEBHOOK_URL
                base_url = (SUBSCRIPTION_URL or WEBHOOK_URL or "").rstrip("/")
                subscription_base_url = base_url if (base_url and "://" in base_url) else ""
                subscription_url = f"{base_url}/sub/{short_uuid}" if (subscription_base_url and short_uuid) else ""
                return APIResponse.success(
                    telegram_linked=tid is not None,
                    is_web=username is not None,
                    username=username or '',
                    account_id=auth.account_id,
                    telegram_id=tid,
                    web_access_enabled=web_access_enabled,
                    short_uuid=short_uuid,
                    subscription_base_url=subscription_base_url,
                    subscription_url=subscription_url,
                )

            return run_async(fetch_status())
        except Exception as e:
            logger.error("Ошибка link-status: %s", e, exc_info=True)
            return APIResponse.internal_error()

    @bp.route('/api/user/avatar', methods=['GET', 'OPTIONS'])
    @require_auth
    def api_user_avatar(auth: AuthContext):
        """Проксирует аватар из Telegram по account_id (telegram identity)."""
        if request.method == 'OPTIONS':
            return handle_options()
        try:
            async def fetch_avatar():
                from ....db.accounts_db import get_telegram_id_for_account
                tid = await get_telegram_id_for_account(auth.account_id)
                if not tid:
                    return None, None
                bot = bot_app.bot
                try:
                    photos = await bot.get_user_profile_photos(user_id=int(tid), limit=1)
                    if not photos or not photos.photos:
                        return None, None
                    largest = photos.photos[-1][-1]
                    tg_file = await bot.get_file(largest.file_id)
                    return tg_file.file_path, None
                except Exception as e:
                    logger.warning(f"get_user_profile_photos/get_file: {e}")
                    return None, None

            file_path, _ = run_async(fetch_avatar())
            if not file_path:
                return Response(status=404)
            from ....config import TELEGRAM_TOKEN
            if not TELEGRAM_TOKEN:
                return Response(status=500)
            url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
            r = requests_lib.get(url, timeout=5)
            if not r.ok:
                return Response(status=502)
            return Response(
                r.content,
                mimetype='image/jpeg',
                headers={'Cache-Control': 'private, max-age=3600'}
            )
        except Exception as e:
            logger.error(f"Ошибка /api/user/avatar: {e}", exc_info=True)
            return Response(status=500)

    @bp.route('/api/user/change-password', methods=['POST', 'OPTIONS'])
    @require_auth
    def api_user_change_password(auth: AuthContext):
        """Смена пароля (веб-пользователь). Требует текущий пароль."""
        if request.method == 'OPTIONS':
            return handle_options()
        try:
            data = request.get_json(silent=True) or {}
            current = (data.get('current_password') or '').strip()
            new_pw = (data.get('new_password') or '').strip()
            if not current:
                return APIResponse.bad_request('Введите текущий пароль')
            if len(new_pw) < 6:
                return APIResponse.bad_request('Новый пароль слишком короткий (минимум 6 символов)')
            from ....db.accounts_db import get_account_password_hash, set_account_password

            async def change_pwd():
                pwd_hash = await get_account_password_hash(auth.account_id)
                if not pwd_hash:
                    return APIResponse.bad_request('Пароль для этого аккаунта не настроен')
                if not check_password_hash(pwd_hash, current):
                    return APIResponse.unauthorized('Неверный текущий пароль')
                if check_password_hash(pwd_hash, new_pw):
                    return APIResponse.bad_request('Новый пароль должен отличаться от текущего')
                new_hash = generate_password_hash(new_pw)
                await set_account_password(auth.account_id, new_hash)
                return APIResponse.success(message='Пароль изменён')

            return run_async(change_pwd())
        except Exception as e:
            logger.error("Ошибка change-password: %s", e, exc_info=True)
            return APIResponse.internal_error()

    @bp.route('/api/user/change-login', methods=['POST', 'OPTIONS'])
    @require_auth
    def api_user_change_login(auth: AuthContext):
        """Смена логина (веб-пользователь). Требует текущий пароль."""
        if request.method == 'OPTIONS':
            return handle_options()
        try:
            data = request.get_json(silent=True) or {}
            current = (data.get('current_password') or '').strip()
            new_login = (data.get('new_login') or '').strip().lower()
            if not current:
                return APIResponse.bad_request('Введите текущий пароль')
            if len(new_login) < 3:
                return APIResponse.bad_request('Логин слишком короткий (минимум 3 символа)')
            from ....db.accounts_db import (
                get_username_for_account,
                get_account_password_hash,
                username_available,
                replace_password_identity,
            )

            async def change_login():
                username = await get_username_for_account(auth.account_id)
                pwd_hash = await get_account_password_hash(auth.account_id)
                if not username or not pwd_hash:
                    return APIResponse.bad_request('Пароль для этого аккаунта не настроен')
                if not check_password_hash(pwd_hash, current):
                    return APIResponse.unauthorized('Неверный текущий пароль')
                cur_username = username.strip().lower()
                if new_login == cur_username:
                    return APIResponse.bad_request('Укажите новый логин, отличный от текущего')
                ok = await username_available(new_login, exclude_account_id=auth.account_id)
                if not ok:
                    return APIResponse.conflict('Этот логин уже занят')
                await replace_password_identity(auth.account_id, new_login)
                return APIResponse.success(message='Логин изменён', username=new_login)

            return run_async(change_login())
        except Exception as e:
            logger.error("Ошибка change-login: %s", e, exc_info=True)
            return APIResponse.internal_error()

    @bp.route('/api/user/unlink-telegram', methods=['POST', 'OPTIONS'])
    @require_auth
    def api_user_unlink_telegram(auth: AuthContext):
        """Отвязка Telegram от аккаунта. Требует текущий пароль (веб-доступ)."""
        if request.method == 'OPTIONS':
            return handle_options()
        try:
            data = request.get_json(silent=True) or {}
            current_password = (data.get('current_password') or '').strip()
            if not current_password:
                return APIResponse.bad_request('Введите текущий пароль')
            from ....db.accounts_db import (
                get_telegram_id_for_account,
                get_account_password_hash,
                delete_identity,
            )

            async def unlink():
                pwd_hash = await get_account_password_hash(auth.account_id)
                if not pwd_hash:
                    return APIResponse.bad_request('Для отвязки Telegram необходимо сначала настроить веб-доступ (логин и пароль)')
                if not check_password_hash(pwd_hash, current_password):
                    return APIResponse.unauthorized('Неверный текущий пароль')
                telegram_id = await get_telegram_id_for_account(auth.account_id)
                if not telegram_id:
                    return APIResponse.bad_request('Telegram не привязан к этому аккаунту')
                await delete_identity(auth.account_id, "telegram", telegram_id)
                from ....services.subscription_service import sync_remnawave_telegram_id
                await sync_remnawave_telegram_id(auth.account_id, None)
                logger.info("Отвязан Telegram %s от account_id=%s", telegram_id, auth.account_id)
                return APIResponse.success(
                    message='Telegram успешно отвязан. Аккаунт переведен в режим веб-доступа.'
                )

            return run_async(unlink())
        except Exception as e:
            logger.error("Ошибка unlink-telegram: %s", e, exc_info=True)
            return APIResponse.internal_error()

    return bp
