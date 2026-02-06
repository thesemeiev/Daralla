"""
Blueprint: /api/user/* and /api/subscriptions.
"""
import asyncio
import datetime
import logging
import os
import secrets
import time
import uuid
from flask import Blueprint, request, jsonify, Response
from werkzeug.security import generate_password_hash, check_password_hash
import requests as requests_lib

from ..webhook_auth import authenticate_request, verify_telegram_init_data

logger = logging.getLogger(__name__)


def _get_servers_from_manager():
    """Fallback: серверы из server_manager (servers_config) когда Remnawave не используется."""
    try:
        from ....context import get_app_context
        ctx = get_app_context()
        server_manager = ctx.server_manager if ctx else None
        if not server_manager:
            return []
        servers_info = []
        for location, servers in server_manager.servers_by_location.items():
            for server in servers:
                server_name = server["name"]
                config = server.get("config", {})
                display_name = config.get("display_name", server_name)
                map_label = config.get("map_label")
                lat = config.get("lat")
                lng = config.get("lng")
                if lat is not None and lng is not None:
                    servers_info.append({
                        "name": server_name,
                        "display_name": display_name,
                        "map_label": map_label,
                        "location": location,
                        "lat": lat,
                        "lng": lng,
                        "usage_count": 0,
                        "usage_percentage": 0,
                        "status": "available",
                    })
        return servers_info
    except (ImportError, AttributeError) as e:
        logger.error("Ошибка получения информации о серверах: %s", e)
        return []


def create_blueprint(bot_app):
    bp = Blueprint('api_user', __name__)

    def _cors_headers():
        return {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json"
        }

    @bp.route('/api/user/register', methods=['POST', 'OPTIONS'])
    def api_user_register():
        """Регистрация/приветствие при первом открытии мини-приложения. Работает по account_id."""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            account_id = authenticate_request()
            if not account_id:
                return jsonify({'error': 'Invalid authentication'}), 401

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from ....db.accounts_db import get_remnawave_mapping, set_remnawave_mapping
                mapping = loop.run_until_complete(get_remnawave_mapping(account_id))
                was_new_user = mapping is None
                short_uuid = mapping.get("remnawave_short_uuid") if mapping else None

                try:
                    from ....services.remnawave_service import load_remnawave_config, RemnawaveClient
                    from ....db.accounts_db import get_telegram_id_for_account
                    cfg = load_remnawave_config()
                    client = RemnawaveClient(cfg)
                    telegram_id = loop.run_until_complete(get_telegram_id_for_account(account_id))
                    if mapping:
                        short_uuid = short_uuid or (mapping.get("remnawave_short_uuid"))
                    else:
                        remna_user = client.get_user_by_telegram_id(telegram_id) if telegram_id else None
                        if remna_user:
                            short_uuid = remna_user.get("shortUuid") or remna_user.get("short_uuid")
                            loop.run_until_complete(set_remnawave_mapping(
                                account_id,
                                remna_user.get("uuid", remna_user.get("id", "")),
                                short_uuid,
                            ))
                        elif telegram_id:
                            import datetime
                            trial_days = 5
                            expire_at = datetime.datetime.utcnow() + datetime.timedelta(days=trial_days)
                            expire_at_iso = expire_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                            create_payload = {
                                "telegramId": int(telegram_id),
                                "username": f"tg_{telegram_id}",
                                "expireAt": expire_at_iso,
                            }
                            created = client.create_user(create_payload)
                            ruuid = created.get("uuid") or created.get("id") or created.get("obj", {}).get("uuid")
                            short_uuid = created.get("shortUuid") or created.get("short_uuid") or (created.get("obj", {}) or {}).get("shortUuid")
                            if ruuid:
                                loop.run_until_complete(set_remnawave_mapping(account_id, str(ruuid), short_uuid))
                except Exception as remna_e:
                    logger.warning("Remnawave create/lookup skipped: %s", remna_e)

                return jsonify({
                    'success': True,
                    'was_new_user': was_new_user,
                    'account_id': account_id,
                    'short_uuid': short_uuid,
                })
            finally:
                loop.close()
                asyncio.set_event_loop(None)
        except Exception as e:
            logger.error("Ошибка регистрации пользователя: %s", e, exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500

    @bp.route('/api/subscriptions', methods=['GET', 'OPTIONS'])
    def api_subscriptions():
        """Подписки пользователя из Remnawave (source of truth)."""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            account_id = authenticate_request()
            if not account_id:
                return jsonify({'error': 'Invalid authentication'}), 401
            from ....services.subscription_service import get_subscriptions_for_account
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                formatted_subs = loop.run_until_complete(get_subscriptions_for_account(account_id))
            finally:
                loop.close()
            return jsonify({
                'success': True,
                'subscriptions': formatted_subs,
                'total': len(formatted_subs),
                'active': len([s for s in formatted_subs if s['status'] == 'active'])
            }), 200, _cors_headers()
        except Exception as e:
            logger.error("Ошибка в API /api/subscriptions: %s", e, exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500, _cors_headers()

    @bp.route('/api/user/payment/create', methods=['POST', 'OPTIONS'])
    def api_user_payment_create():
        """API endpoint для создания платежа (покупка или продление подписки). В БД хранится account_id."""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            account_id = authenticate_request()
            if not account_id:
                return jsonify({'error': 'Invalid authentication'}), 401
            data = request.get_json(silent=True) or {}
            period = data.get('period')
            subscription_id = data.get('subscription_id')
            if not period or period not in ['month', '3month']:
                return jsonify({'error': 'Invalid period. Use "month" or "3month"'}), 400
            from ....prices_config import PRICES
            price = f"{PRICES[period]:.2f}"
            from yookassa import Payment
            from ....db import add_payment, PAYMENTS_DB_PATH
            import aiosqlite
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                async def cancel_old_payments():
                    async with aiosqlite.connect(PAYMENTS_DB_PATH) as db:
                        await db.execute(
                            'UPDATE payments SET status = ? WHERE account_id = ? AND status = ?',
                            ('canceled', str(account_id), 'pending')
                        )
                        await db.commit()
                loop.run_until_complete(cancel_old_payments())
                now = int(datetime.datetime.now().timestamp())
                subscription_uuid = str(uuid.uuid4())
                unique_email = f'{account_id}_{subscription_uuid}'
                payment_period = f"extend_sub_{period}" if subscription_id else period
                payment = Payment.create({
                    "amount": {"value": price, "currency": "RUB"},
                    "confirmation": {"type": "redirect", "return_url": "https://t.me/"},
                    "capture": True,
                    "description": f"VPN {period}",
                    "metadata": {
                        "account_id": account_id,
                        "type": payment_period,
                        "device_limit": 1,
                        "unique_email": unique_email,
                        "price": price,
                    },
                    "receipt": {
                        "customer": {"email": f"{account_id}@vpn.local"},
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
                async def save_payment():
                    await add_payment(
                        payment_id=payment.id,
                        account_id=account_id,
                        status='pending',
                        meta=payment_meta
                    )
                loop.run_until_complete(save_payment())
            finally:
                loop.close()
            return jsonify({
                'success': True,
                'payment_id': payment.id,
                'payment_url': payment.confirmation.confirmation_url,
                'amount': price,
                'period': period
            }), 200, _cors_headers()
        except Exception as e:
            logger.error(f"Ошибка в API /api/user/payment/create: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500, _cors_headers()

    @bp.route('/api/user/payment/status/<payment_id>', methods=['GET', 'OPTIONS'])
    def api_user_payment_status(payment_id):
        """API endpoint для проверки статуса платежа"""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            account_id = authenticate_request()
            if not account_id:
                return jsonify({'error': 'Invalid authentication'}), 401
            from ....db import get_payment_by_id
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                payment_info = loop.run_until_complete(get_payment_by_id(payment_id))
            finally:
                loop.close()
            if not payment_info:
                return jsonify({'error': 'Payment not found'}), 404
            if payment_info.get('account_id') != str(account_id):
                return jsonify({'error': 'Access denied'}), 403
            payload = {
                'success': True,
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
            return jsonify(payload), 200, _cors_headers()
        except Exception as e:
            logger.error(f"Ошибка в API /api/user/payment/status/{payment_id}: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500, _cors_headers()

    @bp.route('/api/user/server-usage', methods=['GET', 'OPTIONS'])
    def api_user_server_usage():
        """Данные о серверах: из Remnawave при наличии, иначе из server_manager (fallback)."""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            account_id = authenticate_request()
            if not account_id:
                return jsonify({'error': 'Invalid authentication'}), 401

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from ....services.remnawave_service import is_remnawave_configured
                from ....services.nodes_display_service import get_remnawave_nodes_for_display

                if is_remnawave_configured():
                    servers_info = loop.run_until_complete(get_remnawave_nodes_for_display())
                else:
                    servers_info = _get_servers_from_manager()
                return jsonify({'success': True, 'servers': servers_info}), 200, _cors_headers()
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Ошибка в API /api/user/server-usage: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500

    @bp.route('/api/user/web-access/setup', methods=['POST', 'OPTIONS'])
    def api_user_web_access_setup():
        """Настройка web-доступа из Mini App (логин + пароль)"""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            data = request.get_json(silent=True) or {}
            init_data = data.get('initData')
            if not init_data:
                return jsonify({'error': 'Telegram data required'}), 400
            telegram_id = verify_telegram_init_data(init_data)
            if not telegram_id:
                return jsonify({'error': 'Invalid authentication'}), 401
            data = request.get_json(silent=True)
            username = (data.get('username') or '').strip().lower()
            password = (data.get('password') or '').strip()
            if len(username) < 3:
                return jsonify({'error': 'Логин слишком короткий (мин. 3 символа)'}), 400
            if len(password) < 6:
                return jsonify({'error': 'Пароль слишком короткий (мин. 6 символов)'}), 400
            from ....db.accounts_db import (
                get_or_create_account_for_telegram,
                replace_password_identity,
                set_account_password,
                username_available,
            )
            password_hash = generate_password_hash(password)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                account_id = loop.run_until_complete(get_or_create_account_for_telegram(telegram_id))
                ok = loop.run_until_complete(username_available(username, exclude_account_id=None))
                if not ok:
                    return jsonify({'error': 'Этот логин уже занят'}), 409
                loop.run_until_complete(replace_password_identity(account_id, username))
                loop.run_until_complete(set_account_password(account_id, password_hash))
                return jsonify({
                    'success': True,
                    'message': f'Web-доступ настроен. Теперь вы можете войти на сайт с логином {username}.',
                    'username': username,
                    'account_id': account_id,
                })
            finally:
                loop.close()
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/user/link-telegram/start', methods=['POST', 'OPTIONS'])
    def api_user_link_telegram_start():
        """Начать привязку Telegram. В state сохраняем str(account_id)."""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            account_id = authenticate_request()
            if not account_id:
                return jsonify({'error': 'Требуется авторизация'}), 401
            from ....db.accounts_db import get_telegram_id_for_account, link_telegram_create_state
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                tid = loop.run_until_complete(get_telegram_id_for_account(account_id))
                if tid:
                    return jsonify({'error': 'Telegram уже привязан'}), 400
                state = loop.run_until_complete(link_telegram_create_state(account_id))
                bot_username = os.getenv('BOT_USERNAME', 'Daralla_bot')
                link = f"https://t.me/{bot_username}?start=link_{state}"
                return jsonify({'success': True, 'link': link, 'state': state})
            finally:
                loop.close()
        except Exception as e:
            logger.error("Ошибка link-telegram/start: %s", e, exc_info=True)
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/user/link-status', methods=['GET', 'OPTIONS'])
    def api_user_link_status():
        """Статус привязки Telegram и веб-доступа по account_id и identities."""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            account_id = authenticate_request()
            if not account_id:
                return jsonify({'error': 'Требуется авторизация'}), 401
            from ....db.accounts_db import (
                get_telegram_id_for_account,
                get_username_for_account,
                get_remnawave_mapping,
                get_account_password_hash,
            )
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                tid = loop.run_until_complete(get_telegram_id_for_account(account_id))
                username = loop.run_until_complete(get_username_for_account(account_id))
                mapping = loop.run_until_complete(get_remnawave_mapping(account_id))
                short_uuid = mapping.get("remnawave_short_uuid") if mapping else None
                pwd_hash = loop.run_until_complete(get_account_password_hash(account_id))
                web_access_enabled = pwd_hash is not None
                from ....config import SUBSCRIPTION_URL, WEBHOOK_URL
                base_url = (SUBSCRIPTION_URL or WEBHOOK_URL or "").rstrip("/")
                subscription_base_url = base_url if (base_url and "://" in base_url) else ""
                subscription_url = f"{base_url}/sub/{short_uuid}" if (subscription_base_url and short_uuid) else ""
                return jsonify({
                    'success': True,
                    'telegram_linked': tid is not None,
                    'is_web': username is not None,
                    'username': username or '',
                    'account_id': account_id,
                    'telegram_id': tid,
                    'web_access_enabled': web_access_enabled,
                    'short_uuid': short_uuid,
                    'subscription_base_url': subscription_base_url,
                    'subscription_url': subscription_url,
                })
            finally:
                loop.close()
        except Exception as e:
            logger.error("Ошибка link-status: %s", e, exc_info=True)
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/user/avatar', methods=['GET', 'OPTIONS'])
    def api_user_avatar():
        """Проксирует аватар из Telegram по account_id (telegram identity)."""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            account_id = authenticate_request()
            if not account_id:
                return Response(status=401)
            from ....db.accounts_db import get_telegram_id_for_account
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                tid = loop.run_until_complete(get_telegram_id_for_account(account_id))
                if not tid:
                    return Response(status=404)
                bot = bot_app.bot
                async def fetch_avatar():
                    try:
                        photos = await bot.get_user_profile_photos(user_id=int(tid), limit=1)
                        if not photos or not photos.photos:
                            return None
                        largest = photos.photos[-1][-1]
                        tg_file = await bot.get_file(largest.file_id)
                        return tg_file.file_path
                    except Exception as e:
                        logger.warning(f"get_user_profile_photos/get_file: {e}")
                        return None
                file_path = loop.run_until_complete(fetch_avatar())
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
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Ошибка /api/user/avatar: {e}", exc_info=True)
            return Response(status=500)

    @bp.route('/api/user/change-password', methods=['POST', 'OPTIONS'])
    def api_user_change_password():
        """Смена пароля (веб-пользователь). Требует текущий пароль."""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            account_id = authenticate_request()
            if not account_id:
                return jsonify({'error': 'Требуется авторизация'}), 401
            data = request.get_json(silent=True) or {}
            current = (data.get('current_password') or '').strip()
            new_pw = (data.get('new_password') or '').strip()
            if not current:
                return jsonify({'error': 'Введите текущий пароль'}), 400
            if len(new_pw) < 6:
                return jsonify({'error': 'Новый пароль слишком короткий (минимум 6 символов)'}), 400
            from ....db.accounts_db import get_account_password_hash, set_account_password
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                pwd_hash = loop.run_until_complete(get_account_password_hash(account_id))
                if not pwd_hash:
                    return jsonify({'error': 'Пароль для этого аккаунта не настроен'}), 400
                if not check_password_hash(pwd_hash, current):
                    return jsonify({'error': 'Неверный текущий пароль'}), 401
                if check_password_hash(pwd_hash, new_pw):
                    return jsonify({'error': 'Новый пароль должен отличаться от текущего'}), 400
                new_hash = generate_password_hash(new_pw)
                loop.run_until_complete(set_account_password(account_id, new_hash))
                return jsonify({'success': True, 'message': 'Пароль изменён'})
            finally:
                loop.close()
        except Exception as e:
            logger.error("Ошибка change-password: %s", e, exc_info=True)
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/user/change-login', methods=['POST', 'OPTIONS'])
    def api_user_change_login():
        """Смена логина (веб-пользователь). Требует текущий пароль."""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            account_id = authenticate_request()
            if not account_id:
                return jsonify({'error': 'Требуется авторизация'}), 401
            data = request.get_json(silent=True) or {}
            current = (data.get('current_password') or '').strip()
            new_login = (data.get('new_login') or '').strip().lower()
            if not current:
                return jsonify({'error': 'Введите текущий пароль'}), 400
            if len(new_login) < 3:
                return jsonify({'error': 'Логин слишком короткий (минимум 3 символа)'}), 400
            from ....db.accounts_db import (
                get_username_for_account,
                get_account_password_hash,
                username_available,
                replace_password_identity,
            )
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                username = loop.run_until_complete(get_username_for_account(account_id))
                pwd_hash = loop.run_until_complete(get_account_password_hash(account_id))
                if not username or not pwd_hash:
                    return jsonify({'error': 'Пароль для этого аккаунта не настроен'}), 400
                if not check_password_hash(pwd_hash, current):
                    return jsonify({'error': 'Неверный текущий пароль'}), 401
                cur_username = username.strip().lower()
                if new_login == cur_username:
                    return jsonify({'error': 'Укажите новый логин, отличный от текущего'}), 400
                ok = loop.run_until_complete(username_available(new_login, exclude_account_id=account_id))
                if not ok:
                    return jsonify({'error': 'Этот логин уже занят'}), 409
                loop.run_until_complete(replace_password_identity(account_id, new_login))
                return jsonify({'success': True, 'message': 'Логин изменён', 'username': new_login})
            finally:
                loop.close()
        except Exception as e:
            logger.error("Ошибка change-login: %s", e, exc_info=True)
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/user/unlink-telegram', methods=['POST', 'OPTIONS'])
    def api_user_unlink_telegram():
        """Отвязка Telegram от аккаунта. Требует текущий пароль (веб-доступ)."""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            account_id = authenticate_request()
            if not account_id:
                return jsonify({'error': 'Требуется авторизация'}), 401
            data = request.get_json(silent=True) or {}
            current_password = (data.get('current_password') or '').strip()
            if not current_password:
                return jsonify({'error': 'Введите текущий пароль'}), 400
            from ....db.accounts_db import (
                get_telegram_id_for_account,
                get_account_password_hash,
                delete_identity,
            )
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                pwd_hash = loop.run_until_complete(get_account_password_hash(account_id))
                if not pwd_hash:
                    return jsonify({'error': 'Для отвязки Telegram необходимо сначала настроить веб-доступ (логин и пароль)'}), 400
                if not check_password_hash(pwd_hash, current_password):
                    return jsonify({'error': 'Неверный текущий пароль'}), 401
                telegram_id = loop.run_until_complete(get_telegram_id_for_account(account_id))
                if not telegram_id:
                    return jsonify({'error': 'Telegram не привязан к этому аккаунту'}), 400
                loop.run_until_complete(delete_identity(account_id, "telegram", telegram_id))
                from ....services.subscription_service import sync_remnawave_telegram_id
                loop.run_until_complete(sync_remnawave_telegram_id(account_id, None))
                logger.info("Отвязан Telegram %s от account_id=%s", telegram_id, account_id)
                return jsonify({
                    'success': True,
                    'message': 'Telegram успешно отвязан. Аккаунт переведен в режим веб-доступа.'
                })
            finally:
                loop.close()
        except Exception as e:
            logger.error("Ошибка unlink-telegram: %s", e, exc_info=True)
            return jsonify({'error': str(e)}), 500

    return bp
