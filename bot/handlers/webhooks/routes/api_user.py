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


def create_blueprint(bot_app):
    bp = Blueprint('api_user', __name__)

    def _cors_headers():
        return {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json"
        }

    @bp.route('/api/user/register', methods=['POST', 'OPTIONS'])
    def api_user_register():
        """Регистрация пользователя при первом открытии мини-приложения."""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            user_id = authenticate_request()
            init_data = request.args.get('initData')
            if not init_data and request.is_json:
                try:
                    data = request.get_json(silent=True)
                    if data:
                        init_data = data.get('initData')
                except Exception:
                    init_data = None
            tg_user_id = None
            if init_data:
                tg_user_id = verify_telegram_init_data(init_data)
            if not user_id and tg_user_id:
                user_id = None
            if not user_id and not tg_user_id:
                return jsonify({'error': 'Invalid authentication'}), 401

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from ....db import is_known_user, register_simple_user
                from ....db.subscribers_db import (
                    get_all_active_subscriptions_by_user,
                    get_or_create_subscriber,
                    create_subscription,
                    is_subscription_active,
                    is_known_telegram_id,
                    mark_telegram_id_known,
                    get_user_by_telegram_id_v2,
                    create_telegram_link,
                    update_user_telegram_id,
                    generate_tg_user_id,
                )
                just_created_tg_user = False
                if not user_id and tg_user_id:
                    _tg_str = str(tg_user_id)
                    _existing = loop.run_until_complete(get_user_by_telegram_id_v2(_tg_str, use_fallback=True))
                    if _existing:
                        user_id = _existing["user_id"]
                    else:
                        user_id = generate_tg_user_id()
                        loop.run_until_complete(register_simple_user(user_id))
                        loop.run_until_complete(create_telegram_link(_tg_str, user_id))
                        loop.run_until_complete(update_user_telegram_id(user_id, _tg_str))
                        just_created_tg_user = True
                        logger.info(f"Регистрация нового TG-first пользователя: user_id={user_id}, telegram_id={_tg_str}")
                if not user_id:
                    return jsonify({'error': 'Invalid authentication'}), 401
                is_web = user_id.startswith('web_')
                was_known_user = loop.run_until_complete(is_known_user(user_id))
                if tg_user_id:
                    was_known_user = was_known_user or loop.run_until_complete(is_known_telegram_id(str(tg_user_id)))
                if just_created_tg_user:
                    was_known_user = False
                if not just_created_tg_user:
                    loop.run_until_complete(register_simple_user(user_id))
                if tg_user_id:
                    loop.run_until_complete(mark_telegram_id_known(str(tg_user_id)))
                trial_created = False
                subscription_id = None
                if not was_known_user and not is_web:
                    try:
                        existing_subs = loop.run_until_complete(get_all_active_subscriptions_by_user(user_id))
                        now = int(time.time())
                        active_subs = [sub for sub in existing_subs if is_subscription_active(sub)]
                        if len(active_subs) == 0:
                            logger.info(f"Создание пробной подписки для нового пользователя: {user_id}")
                            subscriber_id = loop.run_until_complete(get_or_create_subscriber(user_id))
                            expires_at = now + (5 * 24 * 60 * 60)
                            subscription_id, token = loop.run_until_complete(create_subscription(
                                subscriber_id=subscriber_id,
                                period='month',
                                device_limit=1,
                                price=0.0,
                                expires_at=expires_at,
                                name="Пробная подписка"
                            ))
                            trial_created = True
                            logger.info(f"✅ Пробная подписка создана: subscription_id={subscription_id}")
                            def get_managers():
                                try:
                                    from .... import bot as bot_module
                                    return {
                                        'subscription_manager': getattr(bot_module, 'subscription_manager', None),
                                        'server_manager': getattr(bot_module, 'new_client_manager', None)
                                    }
                                except (ImportError, AttributeError):
                                    return {'subscription_manager': None, 'server_manager': None}
                            managers = get_managers()
                            subscription_manager = managers.get('subscription_manager')
                            server_manager = managers.get('server_manager')
                            if subscription_manager and server_manager:
                                unique_email = f"{user_id}_{subscription_id}"
                                all_configured_servers = []
                                for server in server_manager.servers:
                                    server_name = server["name"]
                                    if server.get("x3") is not None:
                                        all_configured_servers.append(server_name)
                                if all_configured_servers:
                                    async def attach_servers():
                                        for server_name in all_configured_servers:
                                            try:
                                                await subscription_manager.attach_server_to_subscription(
                                                    subscription_id=subscription_id,
                                                    server_name=server_name,
                                                    client_email=unique_email,
                                                    client_id=None,
                                                )
                                            except Exception as attach_e:
                                                if "UNIQUE constraint" not in str(attach_e) and "already exists" not in str(attach_e).lower():
                                                    logger.error(f"Ошибка привязки сервера {server_name}: {attach_e}")
                                    loop.run_until_complete(attach_servers())
                                    async def create_clients():
                                        successful = []
                                        for server_name in all_configured_servers:
                                            try:
                                                client_exists, client_created = await subscription_manager.ensure_client_on_server(
                                                    subscription_id=subscription_id,
                                                    server_name=server_name,
                                                    client_email=unique_email,
                                                    user_id=user_id,
                                                    expires_at=expires_at,
                                                    token=token,
                                                    device_limit=1
                                                )
                                                if client_exists:
                                                    successful.append(server_name)
                                            except Exception as e:
                                                logger.error(f"Ошибка создания клиента на {server_name}: {e}")
                                        return successful
                                    successful_servers = loop.run_until_complete(create_clients())
                                    logger.info(f"Пробная подписка: создано на {len(successful_servers)}/{len(all_configured_servers)} серверах")
                    except Exception as e:
                        logger.error(f"Ошибка создания пробной подписки: {e}", exc_info=True)
                return jsonify({
                    'success': True,
                    'was_new_user': not was_known_user,
                    'trial_created': trial_created,
                    'subscription_id': subscription_id
                })
            finally:
                try:
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    if pending:
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except Exception:
                    pass
                finally:
                    loop.close()
                    asyncio.set_event_loop(None)
        except Exception as e:
            logger.error(f"Ошибка регистрации пользователя: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500

    @bp.route('/api/subscriptions', methods=['GET', 'OPTIONS'])
    def api_subscriptions():
        """API endpoint для получения подписок пользователя"""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            user_id = authenticate_request()
            if not user_id:
                return jsonify({'error': 'Invalid authentication'}), 401
            from ....db.subscribers_db import get_all_subscriptions_by_user, is_subscription_active
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                subscriptions = loop.run_until_complete(get_all_subscriptions_by_user(user_id))
            finally:
                loop.close()
            current_time = int(time.time())
            formatted_subs = []
            for sub in subscriptions:
                expires_at = sub['expires_at']
                is_active = is_subscription_active(sub)
                is_expired = expires_at < current_time
                expiry_datetime = datetime.datetime.fromtimestamp(expires_at)
                created_datetime = datetime.datetime.fromtimestamp(sub['created_at'])
                formatted_subs.append({
                    'id': sub['id'],
                    'name': sub.get('name', f"Подписка {sub['id']}"),
                    'status': 'active' if is_active else ('expired' if is_expired else sub['status']),
                    'period': sub['period'],
                    'device_limit': sub['device_limit'],
                    'created_at': sub['created_at'],
                    'created_at_formatted': created_datetime.strftime('%d.%m.%Y %H:%M'),
                    'expires_at': expires_at,
                    'expires_at_formatted': expiry_datetime.strftime('%d.%m.%Y %H:%M'),
                    'price': sub['price'],
                    'token': sub['subscription_token'],
                    'days_remaining': max(0, (expires_at - current_time) // (24 * 60 * 60)) if is_active else 0
                })
            formatted_subs.sort(key=lambda x: (x['status'] != 'active', -x['created_at']))
            return jsonify({
                'success': True,
                'subscriptions': formatted_subs,
                'total': len(formatted_subs),
                'active': len([s for s in formatted_subs if s['status'] == 'active'])
            }), 200, _cors_headers()
        except Exception as e:
            logger.error(f"Ошибка в API /api/subscriptions: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500, _cors_headers()

    @bp.route('/api/user/payment/create', methods=['POST', 'OPTIONS'])
    def api_user_payment_create():
        """API endpoint для создания платежа (покупка или продление подписки)"""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            user_id = authenticate_request()
            if not user_id:
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
                            'UPDATE payments SET status = ? WHERE user_id = ? AND status = ?',
                            ('canceled', user_id, 'pending')
                        )
                        await db.commit()
                loop.run_until_complete(cancel_old_payments())
                now = int(datetime.datetime.now().timestamp())
                subscription_uuid = str(uuid.uuid4())
                unique_email = f'{user_id}_{subscription_uuid}'
                payment_period = f"extend_sub_{period}" if subscription_id else period
                payment = Payment.create({
                    "amount": {"value": price, "currency": "RUB"},
                    "confirmation": {"type": "redirect", "return_url": f"https://t.me/{user_id}"},
                    "capture": True,
                    "description": f"VPN {period} для {user_id}",
                    "metadata": {
                        "user_id": user_id,
                        "type": payment_period,
                        "device_limit": 1,
                        "unique_email": unique_email,
                        "price": price,
                    },
                    "receipt": {
                        "customer": {"email": f"{user_id}@vpn-x3.ru"},
                        "items": [{
                            "description": f"VPN {period} для {user_id}",
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
                        user_id=user_id,
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
            user_id = authenticate_request()
            if not user_id:
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
            if payment_info['user_id'] != user_id:
                return jsonify({'error': 'Access denied'}), 403
            return jsonify({
                'success': True,
                'payment_id': payment_id,
                'status': payment_info['status'],
                'activated': bool(payment_info.get('activated', 0))
            }), 200, _cors_headers()
        except Exception as e:
            logger.error(f"Ошибка в API /api/user/payment/status/{payment_id}: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500, _cors_headers()

    @bp.route('/api/user/subscription/<int:sub_id>/rename', methods=['POST', 'OPTIONS'])
    def api_user_subscription_rename(sub_id):
        """API endpoint для переименования подписки пользователя"""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            user_id = authenticate_request()
            if not user_id:
                return jsonify({'error': 'Invalid authentication'}), 401
            data = request.get_json(silent=True) or {}
            new_name = data.get('name', '').strip()
            if not new_name:
                return jsonify({'error': 'Name is required'}), 400
            from ....db.subscribers_db import get_subscription_by_id, update_subscription_name
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                sub = loop.run_until_complete(get_subscription_by_id(sub_id, user_id))
                if not sub:
                    return jsonify({'error': 'Subscription not found or access denied'}), 404
                loop.run_until_complete(update_subscription_name(sub_id, new_name))
            finally:
                loop.close()
            return jsonify({
                'success': True,
                'message': 'Subscription renamed successfully',
                'name': new_name
            }), 200, _cors_headers()
        except Exception as e:
            logger.error(f"Ошибка в API /api/user/subscription/{sub_id}/rename: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500, _cors_headers()

    @bp.route('/api/user/server-usage', methods=['GET', 'OPTIONS'])
    def api_user_server_usage():
        """API endpoint для получения данных о серверах и их использовании пользователем"""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            user_id = authenticate_request()
            if not user_id:
                return jsonify({'error': 'Invalid authentication'}), 401
            from ....db.subscribers_db import get_user_server_usage
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                server_usage = loop.run_until_complete(get_user_server_usage(user_id))
            finally:
                loop.close()

            def get_servers_info():
                try:
                    from .... import bot as bot_module
                    server_manager = getattr(bot_module, 'server_manager', None)
                    if not server_manager:
                        return []
                    health_status = server_manager.get_server_health_status()
                    servers_info = []
                    for location, servers in server_manager.servers_by_location.items():
                        for server in servers:
                            server_name = server['name']
                            display_name = server['config'].get('display_name', server_name)
                            map_label = server['config'].get('map_label')
                            lat = server['config'].get('lat')
                            lng = server['config'].get('lng')
                            if lat is not None and lng is not None:
                                usage_data = server_usage.get(server_name, {'count': 0, 'percentage': 0})
                                status_info = health_status.get(server_name, {})
                                status = status_info.get('status', 'unknown')
                                servers_info.append({
                                    'name': server_name,
                                    'display_name': display_name,
                                    'map_label': map_label,
                                    'location': location,
                                    'lat': lat,
                                    'lng': lng,
                                    'usage_count': usage_data['count'],
                                    'usage_percentage': usage_data['percentage'],
                                    'status': status
                                })
                    return servers_info
                except (ImportError, AttributeError) as e:
                    logger.error(f"Ошибка получения информации о серверах: {e}")
                    return []
            servers_info = get_servers_info()
            return jsonify({
                'success': True,
                'servers': servers_info
            }), 200, _cors_headers()
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
            user_id = verify_telegram_init_data(init_data)
            if not user_id:
                return jsonify({'error': 'Invalid authentication'}), 401
            data = request.get_json(silent=True)
            username = (data.get('username') or '').strip().lower()
            password = (data.get('password') or '').strip()
            if len(username) < 3:
                return jsonify({'error': 'Логин слишком короткий (мин. 3 символа)'}), 400
            if len(password) < 6:
                return jsonify({'error': 'Пароль слишком короткий (мин. 6 символов)'}), 400
            from ....db.subscribers_db import (
                get_user_by_id, username_available,
                update_user_username, update_user_password
            )
            password_hash = generate_password_hash(password)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                user = loop.run_until_complete(get_user_by_id(user_id))
                if not user:
                    return jsonify({'error': 'Пользователь не найден'}), 404
                ok = loop.run_until_complete(username_available(username, user_id))
                if not ok:
                    return jsonify({'error': 'Этот логин уже занят'}), 409
                loop.run_until_complete(update_user_username(user_id, username))
                loop.run_until_complete(update_user_password(user_id, password_hash))
                return jsonify({
                    'success': True,
                    'message': f'Web-доступ настроен. Теперь вы можете войти на сайт с логином {username}.',
                    'username': username,
                })
            finally:
                loop.close()
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/user/link-telegram/start', methods=['POST', 'OPTIONS'])
    def api_user_link_telegram_start():
        """Начать привязку Telegram (веб-пользователь). Возвращает ссылку t.me/bot?start=link_<state>."""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            user_id = authenticate_request()
            if not user_id:
                return jsonify({'error': 'Требуется авторизация'}), 401
            from ....db.subscribers_db import (
                get_user_by_id, link_telegram_create_state,
                update_user_telegram_id
            )
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                user = loop.run_until_complete(get_user_by_id(user_id))
                if not user:
                    return jsonify({'error': 'Пользователь не найден'}), 404
                if user.get('telegram_id'):
                    return jsonify({'error': 'Telegram уже привязан'}), 400
                state = loop.run_until_complete(link_telegram_create_state(user_id))
                bot_username = os.getenv('BOT_USERNAME', 'Daralla_bot')
                link = f"https://t.me/{bot_username}?start=link_{state}"
                return jsonify({'success': True, 'link': link, 'state': state})
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Ошибка link-telegram/start: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/user/link-status', methods=['GET', 'OPTIONS'])
    def api_user_link_status():
        """Статус привязки Telegram для текущего веб-пользователя."""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            user_id = authenticate_request()
            if not user_id:
                return jsonify({'error': 'Требуется авторизация'}), 401
            from ....db.subscribers_db import get_user_by_id
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                user = loop.run_until_complete(get_user_by_id(user_id))
                if not user:
                    return jsonify({'error': 'Пользователь не найден'}), 404
                uid = user.get('user_id')
                tid = user.get('telegram_id')
                is_web = uid and isinstance(uid, str) and uid.startswith('web_')
                is_tg_first = uid and isinstance(uid, str) and (uid.isdigit() or uid.startswith('tg_'))
                telegram_linked = is_tg_first or (is_web and bool(tid))
                display_tid = tid or (uid if (uid and uid.isdigit()) else None)
                username = user.get('username') or uid or ''
                web_access_enabled = bool(user.get('password_hash'))
                return jsonify({
                    'success': True,
                    'telegram_linked': telegram_linked,
                    'is_web': is_web,
                    'username': username,
                    'user_id': uid,
                    'telegram_id': display_tid,
                    'web_access_enabled': web_access_enabled,
                })
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Ошибка link-status: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/user/avatar', methods=['GET', 'OPTIONS'])
    def api_user_avatar():
        """Проксирует аватар пользователя из Telegram (getUserProfilePhotos). Только для пользователей с привязанным telegram_id."""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            user_id = authenticate_request()
            if not user_id:
                return Response(status=401)
            from ....db.subscribers_db import get_user_by_id
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                user = loop.run_until_complete(get_user_by_id(user_id))
                if not user:
                    return Response(status=404)
                tid = user.get('telegram_id')
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
                token = os.getenv("TELEGRAM_TOKEN")
                if not token:
                    return Response(status=500)
                url = f"https://api.telegram.org/file/bot{token}/{file_path}"
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
            user_id = authenticate_request()
            if not user_id:
                return jsonify({'error': 'Требуется авторизация'}), 401
            data = request.get_json(silent=True) or {}
            current = (data.get('current_password') or '').strip()
            new_pw = (data.get('new_password') or '').strip()
            if not current:
                return jsonify({'error': 'Введите текущий пароль'}), 400
            if len(new_pw) < 6:
                return jsonify({'error': 'Новый пароль слишком короткий (минимум 6 символов)'}), 400
            from ....db.subscribers_db import get_user_by_id, update_user_password
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                user = loop.run_until_complete(get_user_by_id(user_id))
                if not user or not user.get('password_hash'):
                    return jsonify({'error': 'Пароль для этого аккаунта не настроен'}), 400
                if not check_password_hash(user['password_hash'], current):
                    return jsonify({'error': 'Неверный текущий пароль'}), 401
                if check_password_hash(user['password_hash'], new_pw):
                    return jsonify({'error': 'Новый пароль должен отличаться от текущего'}), 400
                new_hash = generate_password_hash(new_pw)
                loop.run_until_complete(update_user_password(user_id, new_hash))
                return jsonify({'success': True, 'message': 'Пароль изменён'})
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Ошибка change-password: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/user/change-login', methods=['POST', 'OPTIONS'])
    def api_user_change_login():
        """Смена логина (веб-пользователь). Требует текущий пароль."""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            user_id = authenticate_request()
            if not user_id:
                return jsonify({'error': 'Требуется авторизация'}), 401
            data = request.get_json(silent=True) or {}
            current = (data.get('current_password') or '').strip()
            new_login = (data.get('new_login') or '').strip().lower()
            if not current:
                return jsonify({'error': 'Введите текущий пароль'}), 400
            if len(new_login) < 3:
                return jsonify({'error': 'Логин слишком короткий (минимум 3 символа)'}), 400
            from ....db.subscribers_db import (
                get_user_by_id, update_user_username,
                username_available,
            )
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                user = loop.run_until_complete(get_user_by_id(user_id))
                if not user or not user.get('password_hash'):
                    return jsonify({'error': 'Пароль для этого аккаунта не настроен'}), 400
                if not check_password_hash(user['password_hash'], current):
                    return jsonify({'error': 'Неверный текущий пароль'}), 401
                cur_username = (user.get('username') or '').strip().lower()
                if new_login == cur_username:
                    return jsonify({'error': 'Укажите новый логин, отличный от текущего'}), 400
                ok = loop.run_until_complete(username_available(new_login, user_id))
                if not ok:
                    return jsonify({'error': 'Этот логин уже занят'}), 409
                loop.run_until_complete(update_user_username(user_id, new_login))
                return jsonify({'success': True, 'message': 'Логин изменён', 'username': new_login})
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Ошибка change-login: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/user/unlink-telegram', methods=['POST', 'OPTIONS'])
    def api_user_unlink_telegram():
        """Отвязка Telegram от веб-аккаунта. Требует текущий пароль."""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            user_id = authenticate_request()
            if not user_id:
                return jsonify({'error': 'Требуется авторизация'}), 401
            data = request.get_json(silent=True) or {}
            current_password = (data.get('current_password') or '').strip()
            if not current_password:
                return jsonify({'error': 'Введите текущий пароль'}), 400
            from ....db.subscribers_db import (
                get_user_by_id, update_user_telegram_id,
                delete_telegram_link, mark_telegram_id_known,
                rename_user_id, get_telegram_chat_id_for_notification,
            )
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                user = loop.run_until_complete(get_user_by_id(user_id))
                if not user:
                    return jsonify({'error': 'Пользователь не найден'}), 404
                if not user.get('password_hash'):
                    return jsonify({'error': 'Для отвязки Telegram необходимо сначала настроить веб-доступ (логин и пароль)'}), 400
                if not check_password_hash(user['password_hash'], current_password):
                    return jsonify({'error': 'Неверный текущий пароль'}), 401
                telegram_id = user.get('telegram_id')
                if telegram_id is not None:
                    telegram_id = str(telegram_id)
                if not telegram_id:
                    _chat_id = loop.run_until_complete(get_telegram_chat_id_for_notification(user_id))
                    if _chat_id is not None:
                        telegram_id = str(_chat_id)
                is_tg_first = user_id.startswith('tg_') or user_id.isdigit()
                if not telegram_id:
                    return jsonify({'error': 'Telegram не привязан к этому аккаунту'}), 400
                if is_tg_first:
                    username = user.get('username')
                    if not username:
                        return jsonify({'error': 'Ошибка: у аккаунта нет логина для превращения в веб-аккаунт. Сначала смените логин.'}), 400
                    new_user_id = f"web_{username}"
                    loop.run_until_complete(rename_user_id(user_id, new_user_id))
                    logger.info(f"Аккаунт {user_id} превращен в {new_user_id} при отвязке TG")
                    user_id = new_user_id
                loop.run_until_complete(delete_telegram_link(telegram_id))
                loop.run_until_complete(mark_telegram_id_known(telegram_id))
                loop.run_until_complete(update_user_telegram_id(user_id, None))
                logger.info(f"Отвязан Telegram {telegram_id} от аккаунта {user_id}. Связь в telegram_links удалена, TG помечен как известный.")
                return jsonify({
                    'success': True,
                    'message': 'Telegram успешно отвязан. Аккаунт переведен в режим веб-доступа.'
                })
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Ошибка unlink-telegram: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500

    return bp
