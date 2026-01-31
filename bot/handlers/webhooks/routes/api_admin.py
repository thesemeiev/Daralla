"""
Blueprint: all /api/admin/* routes.
"""
import logging
import asyncio
import json
import datetime
import time
import concurrent.futures
from flask import Blueprint, request, jsonify, Response
import aiosqlite

from ..webhook_auth import authenticate_request, check_admin_access

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint('api_admin', __name__)

    @bp.route('/api/admin/check', methods=['POST', 'OPTIONS'])
    def api_admin_check():
        """Проверка прав админа"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
    
        try:
            user_id = authenticate_request()
            if not user_id:
                return jsonify({'error': 'Invalid authentication'}), 401
        
            is_admin = check_admin_access(user_id)
        
            return jsonify({
                'success': True,
                'is_admin': is_admin
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/check: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500

    @bp.route('/api/admin/users', methods=['POST', 'OPTIONS'])
    def api_admin_users():
        """Список пользователей с поиском и пагинацией"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
    
        try:
            user_id = authenticate_request()
            if not user_id:
                return jsonify({'error': 'Invalid authentication'}), 401
        
            if not check_admin_access(user_id):
                return jsonify({'error': 'Access denied'}), 403
        
            data = request.get_json(silent=True) or {}
            search = data.get('search', '').strip()
            page = int(data.get('page', 1))
            limit = int(data.get('limit', 20))
        
            from ....db.subscribers_db import DB_PATH
            import aiosqlite
        
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                async def get_users():
                    async with aiosqlite.connect(DB_PATH) as db:
                        db.row_factory = aiosqlite.Row
                    
                        # Базовый запрос
                        base = "SELECT * FROM users WHERE 1=1"
                        params = []
                    
                        # Поиск по user_id, telegram_id, username
                        if search:
                            base += " AND (user_id LIKE ? OR (telegram_id IS NOT NULL AND telegram_id LIKE ?) OR (username IS NOT NULL AND username LIKE ?))"
                            search_pattern = f"%{search}%"
                            params.extend([search_pattern, search_pattern, search_pattern])
                    
                        # Подсчет общего количества
                        count_query = f"SELECT COUNT(*) as count FROM ({base})"
                        async with db.execute(count_query, params) as cur:
                            row = await cur.fetchone()
                            total = row['count'] if row else 0
                    
                        # Получение данных с пагинацией
                        base += " ORDER BY last_seen DESC LIMIT ? OFFSET ?"
                        params.extend([limit, (page - 1) * limit])
                    
                        async with db.execute(base, params) as cur:
                            rows = await cur.fetchall()
                            users = []
                            for row in rows:
                                async with db.execute(
                                    "SELECT COUNT(*) as count FROM subscriptions s JOIN users u ON s.subscriber_id = u.id WHERE u.user_id = ?",
                                    (row['user_id'],)
                                ) as sub_cur:
                                    sub_row = await sub_cur.fetchone()
                                    sub_count = sub_row['count'] if sub_row else 0
                            
                                users.append({
                                    'id': row['id'],
                                    'user_id': row['user_id'],
                                    'telegram_id': row['telegram_id'] if 'telegram_id' in row.keys() else None,
                                    'username': row['username'] if 'username' in row.keys() else None,
                                    'first_seen': row['first_seen'],
                                    'last_seen': row['last_seen'],
                                    'subscriptions_count': sub_count
                                })
                        
                            return users, total
            
                users, total = loop.run_until_complete(get_users())
            finally:
                loop.close()
        
            return jsonify({
                'success': True,
                'users': users,
                'total': total,
                'page': page,
                'limit': limit,
                'pages': (total + limit - 1) // limit if limit > 0 else 0
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/users: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500

    @bp.route('/api/admin/user/<user_id_param>', methods=['POST', 'OPTIONS'])
    def api_admin_user_info(user_id_param):
        """Информация о пользователе"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
    
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
        
            data = request.get_json(silent=True) or {}
        
            from ....db.subscribers_db import get_user_by_id, get_all_subscriptions_by_user, resolve_user_by_query
            from ....db.payments_db import get_payments_by_user
        
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                user = loop.run_until_complete(resolve_user_by_query(user_id_param))
                if not user:
                    return jsonify({'error': 'User not found'}), 404
                user_id_resolved = user['user_id']
                subscriptions = loop.run_until_complete(get_all_subscriptions_by_user(user_id_resolved))
                payments = loop.run_until_complete(get_payments_by_user(user_id_resolved, limit=10))
            finally:
                loop.close()
        
            import datetime
            import time
            current_time = int(time.time())
        
            # Форматируем подписки
            from ....db.subscribers_db import is_subscription_active
        
            formatted_subs = []
            for sub in subscriptions:
                expires_at = sub['expires_at']
                is_active = is_subscription_active(sub)
            
                formatted_subs.append({
                    'id': sub['id'],
                    'name': sub.get('name', f"Подписка {sub['id']}"),
                    'status': sub['status'],
                    'is_active': is_active,
                    'period': sub['period'],
                    'device_limit': sub['device_limit'],
                    'created_at': sub['created_at'],
                    'created_at_formatted': datetime.datetime.fromtimestamp(sub['created_at']).strftime('%d.%m.%Y %H:%M'),
                    'expires_at': expires_at,
                    'expires_at_formatted': datetime.datetime.fromtimestamp(expires_at).strftime('%d.%m.%Y %H:%M'),
                    'price': sub['price'],
                    'token': sub['subscription_token']
                })
        
            # Форматируем платежи
            formatted_payments = []
            for payment in payments:
                # Безопасно получаем данные из payment
                payment_id = payment.get('payment_id') or payment.get('id', 'N/A')
                status = payment.get('status', 'unknown')
                created_at = payment.get('created_at', 0)
            
                # amount может быть в meta (как price или amount) или отсутствовать
                amount = 0
                meta = payment.get('meta', {})
                if isinstance(meta, dict):
                    amount = meta.get('price') or meta.get('amount', 0)
                elif isinstance(meta, str):
                    try:
                        import json
                        meta_dict = json.loads(meta)
                        amount = meta_dict.get('price') or meta_dict.get('amount', 0)
                    except:
                        amount = 0
            
                # Преобразуем строку в число, если нужно
                if isinstance(amount, str):
                    try:
                        amount = float(amount)
                    except (ValueError, TypeError):
                        amount = 0
            
                formatted_payments.append({
                    'id': payment_id,
                    'amount': amount,
                    'status': status,
                    'created_at': created_at,
                    'created_at_formatted': datetime.datetime.fromtimestamp(created_at).strftime('%d.%m.%Y %H:%M') if created_at else 'N/A'
                })
        
            return jsonify({
                'success': True,
                'user': {
                    'user_id': user['user_id'],
                    'telegram_id': user.get('telegram_id'),
                    'username': user.get('username'),
                    'first_seen': user['first_seen'],
                    'first_seen_formatted': datetime.datetime.fromtimestamp(user['first_seen']).strftime('%d.%m.%Y %H:%M'),
                    'last_seen': user['last_seen'],
                    'last_seen_formatted': datetime.datetime.fromtimestamp(user['last_seen']).strftime('%d.%m.%Y %H:%M')
                },
                'subscriptions': formatted_subs,
                'payments': formatted_payments
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/user: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500

    @bp.route('/api/admin/user/<user_id_param>/create-subscription', methods=['POST', 'OPTIONS'])
    def api_admin_user_create_subscription(user_id_param):
        """Создание подписки для пользователя администратором"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
    
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
        
            data = request.get_json(silent=True) or {}
        
            # Получаем параметры из запроса
            period = data.get('period', 'month')  # month или 3month
            device_limit = int(data.get('device_limit', 1))
            name = data.get('name') or None  # Опционально
            expires_at = data.get('expires_at')  # Опционально, timestamp
        
            if period not in ('month', '3month'):
                return jsonify({'error': 'Invalid period. Must be "month" or "3month"'}), 400
        
            # Получаем subscription_manager и new_client_manager
            def get_managers():
                try:
                    from .... import bot as bot_module
                    return {
                        'subscription_manager': getattr(bot_module, 'subscription_manager', None),
                        'new_client_manager': getattr(bot_module, 'new_client_manager', None)
                    }
                except (ImportError, AttributeError):
                    return {'subscription_manager': None, 'new_client_manager': None}
        
            managers = get_managers()
            subscription_manager = managers['subscription_manager']
            new_client_manager = managers['new_client_manager']
        
            if not subscription_manager:
                return jsonify({'error': 'Subscription manager not available'}), 503
        
            if not new_client_manager:
                return jsonify({'error': 'New client manager not available'}), 503
        
            # Создаем подписку
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Если указана дата истечения, используем её, иначе рассчитываем от периода
                if expires_at:
                    expires_at_timestamp = int(expires_at)
                else:
                    import time
                    days = 90 if period == "3month" else 30
                    expires_at_timestamp = int(time.time()) + days * 24 * 60 * 60
            
                # Создаем подписку в БД
                price = 0.0  # Бесплатно (выдано админом)
            
                sub_dict, token = loop.run_until_complete(
                    subscription_manager.create_subscription_for_user(
                        user_id=user_id_param,
                        period=period,
                        device_limit=device_limit,
                        price=price,
                        name=name
                    )
                )
            
                subscription_id = sub_dict['id']
            
                # Если была указана дата истечения, обновляем её
                if expires_at:
                    from ....db.subscribers_db import update_subscription_expiry
                    loop.run_until_complete(update_subscription_expiry(subscription_id, expires_at_timestamp))
                    expires_at_final = expires_at_timestamp
                    logger.info(f"Дата истечения обновлена на {expires_at_timestamp} для подписки {subscription_id}")
                else:
                    expires_at_final = sub_dict['expires_at']
            
                logger.info(f"✅ Подписка создана в БД: subscription_id={subscription_id}, user_id={user_id_param}, period={period}")
            
                # Получаем все серверы из конфигурации
                all_configured_servers = []
                for server in new_client_manager.servers:
                    server_name = server["name"]
                    if server.get("x3") is not None:
                        all_configured_servers.append(server_name)
            
                successful_servers = []
                failed_servers = []
            
                if all_configured_servers:
                    # Генерируем уникальный email для клиента
                    unique_email = f"{user_id_param}_{subscription_id}"
                
                    logger.info(f"Создание клиентов на {len(all_configured_servers)} серверах для подписки {subscription_id}")
                
                    # Привязываем все серверы к подписке в БД и создаем клиентов
                    async def attach_servers_and_create_clients():
                        # Привязываем все серверы к подписке в БД
                        for server_name in all_configured_servers:
                            try:
                                await subscription_manager.attach_server_to_subscription(
                                    subscription_id=subscription_id,
                                    server_name=server_name,
                                    client_email=unique_email,
                                    client_id=None,
                                )
                                logger.info(f"Сервер {server_name} привязан к подписке {subscription_id}")
                            except Exception as attach_e:
                                if "UNIQUE constraint" in str(attach_e) or "already exists" in str(attach_e).lower():
                                    logger.info(f"Сервер {server_name} уже привязан к подписке {subscription_id}")
                                else:
                                    logger.error(f"Ошибка привязки сервера {server_name}: {attach_e}")
                    
                        # Создаем клиентов на всех серверах
                        for server_name in all_configured_servers:
                            try:
                                client_exists, client_created = await subscription_manager.ensure_client_on_server(
                                    subscription_id=subscription_id,
                                    server_name=server_name,
                                    client_email=unique_email,
                                    user_id=user_id_param,
                                    expires_at=expires_at_final,
                                    token=token,
                                    device_limit=device_limit
                                )
                            
                                if client_exists:
                                    successful_servers.append({'server': server_name, 'created': client_created})
                                    if client_created:
                                        logger.info(f"✅ Клиент создан на сервере {server_name}")
                                    else:
                                        logger.info(f"Клиент уже существует на сервере {server_name}")
                                else:
                                    failed_servers.append({'server': server_name, 'error': 'Failed to create client'})
                                    logger.warning(f"Не удалось создать клиента на сервере {server_name} (будет создан при синхронизации)")
                            except Exception as e:
                                failed_servers.append({'server': server_name, 'error': str(e)})
                                logger.error(f"Ошибка создания клиента на сервере {server_name}: {e}")
                
                    loop.run_until_complete(attach_servers_and_create_clients())
            
                import datetime
            
                return jsonify({
                    'success': True,
                    'subscription': {
                        'id': subscription_id,
                        'name': sub_dict.get('name', f"Подписка {subscription_id}"),
                        'status': sub_dict['status'],
                        'period': period,
                        'device_limit': device_limit,
                        'expires_at': expires_at_final,
                        'expires_at_formatted': datetime.datetime.fromtimestamp(expires_at_final).strftime('%d.%m.%Y %H:%M'),
                        'token': token
                    },
                    'successful_servers': successful_servers,
                    'failed_servers': failed_servers
                }), 200, {
                    "Access-Control-Allow-Origin": "*",
                    "Content-Type": "application/json"
                }
            finally:
                loop.close()
            
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/user/create-subscription: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error', 'details': str(e)}), 500, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }

    @bp.route('/api/admin/subscription/<int:sub_id>', methods=['POST', 'OPTIONS'])
    def api_admin_subscription_info(sub_id):
        """Информация о подписке"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
    
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
        
            data = request.get_json(silent=True) or {}
        
            from ....db.subscribers_db import get_subscription_by_id_only, get_subscription_servers
        
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                sub = loop.run_until_complete(get_subscription_by_id_only(sub_id))
                if not sub:
                    return jsonify({'error': 'Subscription not found'}), 404
            
                servers = loop.run_until_complete(get_subscription_servers(sub_id))
            finally:
                loop.close()
        
            import datetime
        
            return jsonify({
                'success': True,
                'subscription': {
                    'id': sub['id'],
                    'name': sub.get('name', f"Подписка {sub['id']}"),
                    'status': sub['status'],
                    'period': sub['period'],
                    'device_limit': sub['device_limit'],
                    'created_at': sub['created_at'],
                    'created_at_formatted': datetime.datetime.fromtimestamp(sub['created_at']).strftime('%d.%m.%Y %H:%M'),
                    'expires_at': sub['expires_at'],
                    'expires_at_formatted': datetime.datetime.fromtimestamp(sub['expires_at']).strftime('%d.%m.%Y %H:%M'),
                    'price': sub['price'],
                    'token': sub['subscription_token']
                },
                'servers': servers
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/subscription: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500

    @bp.route('/api/admin/subscription/<int:sub_id>/update', methods=['POST', 'OPTIONS'])
    def api_admin_subscription_update(sub_id):
        """Обновление подписки"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
    
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
        
            data = request.get_json(silent=True) or {}
        
            # Получаем данные для обновления
            updates = {}
            if 'name' in data:
                updates['name'] = data['name']
            if 'expires_at' in data:
                updates['expires_at'] = int(data['expires_at'])
            if 'device_limit' in data:
                updates['device_limit'] = int(data['device_limit'])
            if 'status' in data:
                updates['status'] = data['status']
        
            if not updates:
                return jsonify({'error': 'No fields to update'}), 400
        
            from ....db.subscribers_db import get_subscription_by_id_only, get_subscription_servers, update_subscription_name, update_subscription_expiry, update_subscription_status, DB_PATH
            import aiosqlite
        
            # Создаем новый event loop, но НЕ устанавливаем его глобально для потока
            # Это предотвращает конфликты при многопоточных запросах Flask
            loop = asyncio.new_event_loop()
            try:
                # Проверяем существование подписки
                sub = loop.run_until_complete(get_subscription_by_id_only(sub_id))
                if not sub:
                    return jsonify({'error': 'Subscription not found'}), 404
            
                # Сохраняем старые значения для синхронизации
                old_status = sub['status']
                old_expires_at = sub['expires_at']
                old_device_limit = sub['device_limit']
            
                # Проверяем изменение статуса: запрещаем ручное изменение active ↔ expired
                if 'status' in updates:
                    new_status = updates['status']
                    # Запрещаем ручное изменение active ↔ expired (они управляются автоматически через expires_at)
                    if (old_status in ('active', 'expired') and new_status in ('active', 'expired') and old_status != new_status):
                        return jsonify({
                            'error': 'Нельзя вручную менять статус между "active" и "expired". Статус обновляется автоматически при изменении даты истечения (expires_at).'
                        }), 400
                    # Разрешаем только изменение на deleted (ручное управление)
                    if new_status != 'deleted' and old_status == 'deleted':
                        return jsonify({
                            'error': f'Нельзя изменить статус "{old_status}" на "{new_status}". Статус "deleted" является финальным.'
                        }), 400
            
                # Обновляем поля в БД
                if 'name' in updates:
                    loop.run_until_complete(update_subscription_name(sub_id, updates['name']))
            
                # expires_at обновляется ПЕРЕД статусом, чтобы автоматическое обновление статуса сработало
                if 'expires_at' in updates:
                    loop.run_until_complete(update_subscription_expiry(sub_id, updates['expires_at']))
            
                if 'device_limit' in updates:
                    async def update_device_limit():
                        async with aiosqlite.connect(DB_PATH) as db:
                            await db.execute(
                                "UPDATE subscriptions SET device_limit = ? WHERE id = ?",
                                (updates['device_limit'], sub_id)
                            )
                            await db.commit()
                    loop.run_until_complete(update_device_limit())
            
                # Статус обновляется последним (только для deleted, active/expired управляются через expires_at)
                if 'status' in updates:
                    new_status = updates['status']
                    # Обновляем только если это deleted
                    if new_status == 'deleted':
                        loop.run_until_complete(update_subscription_status(sub_id, new_status))
                    # Если пытались установить active/expired - игнорируем (уже обновлено через expires_at)
            
                # Получаем обновленную подписку
                updated_sub = loop.run_until_complete(get_subscription_by_id_only(sub_id))
            
                # Синхронизация с X-UI серверами
                # Передаем loop явно, чтобы избежать проблем с get_event_loop()
                async def sync_with_servers(executor_loop):
                    # Получаем менеджеры из глобальных переменных
                    from ..payment_processors import get_globals
                    managers = get_globals()
                    server_manager = managers.get('server_manager')
                    subscription_manager = managers.get('subscription_manager')
                
                    if not server_manager or not subscription_manager:
                        logger.warning("server_manager или subscription_manager не доступны для синхронизации")
                        return
                
                    # Получаем список серверов подписки
                    servers = await get_subscription_servers(sub_id)
                    if not servers:
                        logger.info(f"Подписка {sub_id} не имеет привязанных серверов, синхронизация не требуется")
                        return
                
                    # Получаем user_id из subscriber_id
                    subscriber_id = updated_sub.get('subscriber_id')
                    if not subscriber_id:
                        logger.warning(f"Подписка {sub_id} не имеет subscriber_id, синхронизация невозможна")
                        return
                
                    # Получаем user_id из таблицы users
                    async def get_user_id_from_subscriber():
                        async with aiosqlite.connect(DB_PATH) as db:
                            db.row_factory = aiosqlite.Row
                            async with db.execute("SELECT user_id FROM users WHERE id = ?", (subscriber_id,)) as cur:
                                row = await cur.fetchone()
                                return row['user_id'] if row else None
                
                    user_id = await get_user_id_from_subscriber()
                    if not user_id:
                        logger.warning(f"Не найден user_id для subscriber_id={subscriber_id}, синхронизация невозможна")
                        return
                
                    new_status = updated_sub['status']  # Используем актуальный статус (может быть обновлен автоматически через expires_at)
                    new_expires_at = updated_sub['expires_at']
                    new_device_limit = updated_sub['device_limit']
                    token = updated_sub['subscription_token']
                
                    # 1. Если статус изменился на expired/deleted - удаляем клиентов
                    # Проверяем изменение статуса (может быть изменен автоматически через expires_at)
                    if new_status in ['expired', 'deleted']:
                        if old_status != new_status:
                            logger.info(f"Статус подписки {sub_id} изменился на {new_status}, удаляем клиентов с серверов")
                        
                            # Выполняем удаление с общим таймаутом на всю операцию
                            async def delete_clients_with_timeout():
                                import asyncio
                                deleted_count = 0
                                failed_count = 0
                            
                                for server_info in servers:
                                    server_name = server_info['server_name']
                                    client_email = server_info['client_email']
                                
                                    try:
                                        xui, _ = server_manager.get_server_by_name(server_name)
                                        if xui:
                                            # Выполняем удаление в отдельной задаче с таймаутом
                                            try:
                                                # Используем ThreadPoolExecutor для выполнения синхронного deleteClient
                                                # Это предотвращает проблемы с переиспользованием default executor
                                                import concurrent.futures
                                                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                                                    future = executor.submit(xui.deleteClient, client_email, 5)
                                                    # Обертываем future в asyncio.Future для использования с await
                                                    asyncio_future = asyncio.wrap_future(future, loop=executor_loop)
                                                    await asyncio.wait_for(asyncio_future, timeout=8.0)
                                                logger.info(f"✅ Удален клиент {client_email} с сервера {server_name} (подписка {sub_id}, статус изменен на {new_status})")
                                                deleted_count += 1
                                            except asyncio.TimeoutError:
                                                logger.warning(f"Таймаут при удалении клиента {client_email} с сервера {server_name}")
                                                failed_count += 1
                                            except Exception as delete_e:
                                                # Клиент может быть уже удален или сервер недоступен - это нормально
                                                logger.warning(f"Не удалось удалить клиента {client_email} с сервера {server_name}: {delete_e}")
                                                failed_count += 1
                                        else:
                                            logger.warning(f"Сервер {server_name} не найден")
                                            failed_count += 1
                                    except Exception as e:
                                        logger.error(f"Ошибка при попытке удаления клиента {client_email} с сервера {server_name}: {e}")
                                        failed_count += 1
                            
                                logger.info(f"Удаление клиентов завершено: успешно={deleted_count}, ошибок={failed_count}")
                                return deleted_count, failed_count
                        
                            # Выполняем удаление с общим таймаутом 30 секунд на все серверы
                            deleted_count = 0
                            failed_count = 0
                            try:
                                deleted_count, failed_count = await asyncio.wait_for(delete_clients_with_timeout(), timeout=30.0)
                            except asyncio.TimeoutError:
                                logger.error(f"Таймаут при удалении клиентов для подписки {sub_id} (превышен общий таймаут 30 секунд)")
                                failed_count = len(servers)  # Считаем все как неудачные при таймауте
                            except Exception as e:
                                logger.error(f"Ошибка при удалении клиентов для подписки {sub_id}: {e}")
                                failed_count = len(servers)
                        
                            # Удаляем связи подписки с серверами из БД после удаления клиентов
                            # ВАЖНО: Удаляем связи только если удаление клиентов прошло успешно
                            # или если есть частичные успехи (не все серверы недоступны)
                            from ....db.subscribers_db import remove_subscription_server
                            removed_connections = 0
                            failed_connections = 0
                        
                            # Если были успешные удаления или не все серверы недоступны - удаляем связи
                            # Это безопасно, так как если клиент не удалился, cleanup_orphaned_clients его удалит позже
                            if deleted_count > 0 or failed_count < len(servers):
                                for server_info in servers:
                                    server_name = server_info['server_name']
                                    client_email = server_info['client_email']
                                    try:
                                        await remove_subscription_server(sub_id, server_name)
                                        logger.info(f"✅ Удалена связь подписки {sub_id} с сервером {server_name} (клиент: {client_email}, статус изменен на {new_status})")
                                        removed_connections += 1
                                    except Exception as e:
                                        logger.error(f"❌ Ошибка удаления связи подписки {sub_id} с сервером {server_name} (клиент: {client_email}): {e}")
                                        failed_connections += 1
                            
                                if removed_connections > 0:
                                    logger.info(f"Удалено связей из БД: {removed_connections}, ошибок: {failed_connections}")
                            else:
                                logger.warning(f"Не удалось удалить клиентов ни с одного сервера для подписки {sub_id}, связи не удаляются из БД (будут удалены при следующей синхронизации)")
                
                    # 2. Если статус изменился на active - создаем/восстанавливаем клиентов
                    # (может быть изменен автоматически через expires_at)
                    elif new_status == 'active' and old_status != 'active' and old_status != 'deleted':
                        logger.info(f"Статус подписки {sub_id} изменился на active, создаем/восстанавливаем клиентов")
                        for server_info in servers:
                            server_name = server_info['server_name']
                            client_email = server_info['client_email']
                            try:
                                # Используем ensure_client_on_server для создания/обновления клиента
                                await subscription_manager.ensure_client_on_server(
                                    subscription_id=sub_id,
                                    server_name=server_name,
                                    client_email=client_email,
                                    user_id=user_id,
                                    expires_at=new_expires_at,
                                    token=token,
                                    device_limit=new_device_limit
                                )
                                logger.info(f"Клиент {client_email} создан/обновлен на сервере {server_name}")
                            except Exception as e:
                                logger.error(f"Ошибка создания/обновления клиента {client_email} на сервере {server_name}: {e}")
                
                    # 3. Если изменилась дата истечения или лимит устройств - обновляем клиентов
                    # (статус может быть автоматически обновлен через expires_at)
                    if ('expires_at' in updates or 'device_limit' in updates) and new_status == 'active':
                        # Проверяем, что статус не изменился с неактивного на активный (это обрабатывается в пункте 2)
                        if old_status == 'active' or (old_status == 'expired' and 'expires_at' in updates):
                            logger.info(f"Обновление клиентов подписки {sub_id}: expires_at или device_limit изменились")
                            for server_info in servers:
                                server_name = server_info['server_name']
                                client_email = server_info['client_email']
                                try:
                                    xui, _ = server_manager.get_server_by_name(server_name)
                                    if xui:
                                        # Обновляем время истечения
                                        if 'expires_at' in updates:
                                            import time
                                            xui.setClientExpiry(client_email, new_expires_at)
                                            logger.debug(f"Обновлено время истечения для {client_email} на {server_name}: {new_expires_at}")
                                    
                                        # Обновляем лимит устройств
                                        if 'device_limit' in updates:
                                            xui.updateClientLimitIp(client_email, new_device_limit)
                                            logger.debug(f"Обновлен лимит устройств для {client_email} на {server_name}: {new_device_limit}")
                                except Exception as e:
                                    logger.error(f"Ошибка обновления клиента {client_email} на сервере {server_name}: {e}")
            
                # Выполняем синхронизацию, передавая loop явно
                # Используем таймаут для предотвращения зависания
                sync_task = None
                try:
                    # Создаем задачу синхронизации
                    sync_task = loop.create_task(sync_with_servers(loop))
                    # Выполняем с таймаутом
                    loop.run_until_complete(asyncio.wait_for(sync_task, timeout=60.0))
                except asyncio.TimeoutError:
                    logger.error(f"Таймаут при синхронизации подписки {sub_id} (превышен лимит 60 секунд)")
                    # Отменяем задачу при таймауте
                    if sync_task and not sync_task.done():
                        sync_task.cancel()
                except Exception as sync_e:
                    logger.error(f"Ошибка при синхронизации подписки {sub_id}: {sync_e}", exc_info=True)
                    # Отменяем задачу при ошибке
                    if sync_task and not sync_task.done():
                        sync_task.cancel()
            
            finally:
                # Корректно закрываем loop, отменяя все pending задачи
                try:
                    # Получаем все pending задачи
                    try:
                        pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
                        if pending:
                            logger.debug(f"Отменяем {len(pending)} pending задач перед закрытием loop")
                            for task in pending:
                                if not task.done():
                                    task.cancel()
                        
                            # Ждем завершения отмененных задач с таймаутом
                            if pending:
                                try:
                                    # Используем gather с return_exceptions, чтобы не падать на ошибках
                                    loop.run_until_complete(
                                        asyncio.wait_for(
                                            asyncio.gather(*pending, return_exceptions=True),
                                            timeout=1.0
                                        )
                                    )
                                except (asyncio.TimeoutError, RuntimeError):
                                    # Игнорируем таймауты и ошибки при отмене задач
                                    pass
                    except RuntimeError as e:
                        # Loop может быть уже закрыт или в неправильном состоянии
                        if "Event loop is closed" not in str(e) and "This event loop is already running" not in str(e):
                            logger.debug(f"Ошибка при получении задач: {e}")
                except Exception as e:
                    logger.debug(f"Ошибка при закрытии event loop: {e}")
                finally:
                    try:
                        # Убеждаемся, что loop закрыт
                        if not loop.is_closed():
                            loop.close()
                    except Exception as e:
                        logger.debug(f"Ошибка при финальном закрытии loop: {e}")
        
            import datetime
        
            return jsonify({
                'success': True,
                'subscription': {
                    'id': updated_sub['id'],
                    'name': updated_sub.get('name', f"Подписка {updated_sub['id']}"),
                    'status': updated_sub['status'],
                    'period': updated_sub['period'],
                    'device_limit': updated_sub['device_limit'],
                    'created_at': updated_sub['created_at'],
                    'created_at_formatted': datetime.datetime.fromtimestamp(updated_sub['created_at']).strftime('%d.%m.%Y %H:%M'),
                    'expires_at': updated_sub['expires_at'],
                    'expires_at_formatted': datetime.datetime.fromtimestamp(updated_sub['expires_at']).strftime('%d.%m.%Y %H:%M'),
                    'price': updated_sub['price'],
                    'token': updated_sub['subscription_token']
                }
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/subscription/update: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500

    @bp.route('/api/admin/subscription/<int:sub_id>/sync', methods=['POST', 'OPTIONS'])
    def api_admin_subscription_sync(sub_id):
        """Синхронизация подписки с X-UI серверами"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
    
        data = {}
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
        
            data = request.get_json(silent=True) or {}
        
            from ....db.subscribers_db import get_subscription_by_id_only, get_subscription_servers
        
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                sub = loop.run_until_complete(get_subscription_by_id_only(sub_id))
                if not sub:
                    return jsonify({'error': 'Subscription not found'}), 404
            
                servers = loop.run_until_complete(get_subscription_servers(sub_id))
            
                # Получаем subscription_manager
                def get_subscription_manager():
                    try:
                        from .... import bot as bot_module
                        return getattr(bot_module, 'subscription_manager', None)
                    except (ImportError, AttributeError):
                        return None
            
                subscription_manager = get_subscription_manager()
                if not subscription_manager:
                    return jsonify({'error': 'Subscription manager not available'}), 503
            
                # Получаем user_id из подписки
                async def get_user_id_from_sub():
                    import aiosqlite
                    from ....db.subscribers_db import DB_PATH
                    async with aiosqlite.connect(DB_PATH) as db:
                        db.row_factory = aiosqlite.Row
                        async with db.execute(
                            "SELECT u.user_id FROM users u JOIN subscriptions s ON u.id = s.subscriber_id WHERE s.id = ?",
                            (sub_id,)
                        ) as cur:
                            row = await cur.fetchone()
                            return row['user_id'] if row else ''
            
                user_id = loop.run_until_complete(get_user_id_from_sub())
            
                # Синхронизируем с каждым сервером
                async def sync_all_servers():
                    sync_results = []
                    for server_info in servers:
                        server_name = server_info['server_name']
                        client_email = server_info['client_email']
                    
                        try:
                            # Синхронизируем основные данные (expires_at, device_limit)
                            await subscription_manager.ensure_client_on_server(
                                subscription_id=sub_id,
                                server_name=server_name,
                                client_email=client_email,
                                user_id=user_id,
                                expires_at=sub['expires_at'],
                                token=sub['subscription_token'],
                                device_limit=sub['device_limit']
                            )
                        
                            # Синхронизируем имя подписки (name -> subId на сервере)
                            # Получаем имя подписки из БД
                            subscription_name = sub.get('name', sub['subscription_token'])
                        
                            # Получаем X-UI сервер для обновления имени
                            xui, resolved_name = subscription_manager.server_manager.get_server_by_name(server_name)
                            if xui:
                                try:
                                    # Проверяем текущее имя на сервере
                                    client_info = xui.get_client_info(client_email)
                                    if client_info:
                                        current_sub_id = client_info['client'].get('subId', '')
                                        # Если имя отличается, синхронизируем
                                        if current_sub_id != subscription_name:
                                            logger.info(
                                                f"Синхронизация имени подписки на сервере {server_name}: "
                                                f"'{current_sub_id}' -> '{subscription_name}'"
                                            )
                                            xui.updateClientName(client_email, subscription_name)
                                            logger.info(f"Имя подписки синхронизировано на сервере {server_name}")
                                        else:
                                            logger.debug(f"Имя подписки на сервере {server_name} уже совпадает: '{subscription_name}'")
                                except Exception as name_sync_e:
                                    logger.warning(f"Ошибка синхронизации имени подписки на сервере {server_name}: {name_sync_e}")
                        
                            sync_results.append({
                                'server': server_name,
                                'status': 'success'
                            })
                        except Exception as e:
                            logger.error(f"Ошибка синхронизации с сервером {server_name}: {e}")
                            sync_results.append({
                                'server': server_name,
                                'status': 'error',
                                'error': str(e)
                            })
                    return sync_results
            
                sync_results = loop.run_until_complete(sync_all_servers())
            finally:
                loop.close()
        
            return jsonify({
                'success': True,
                'sync_results': sync_results
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/subscription/sync: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500

    @bp.route('/api/admin/subscription/<int:sub_id>/delete', methods=['POST', 'OPTIONS'])
    def api_admin_subscription_delete(sub_id):
        """Удаление подписки"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
    
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
        
            data = request.get_json(silent=True) or {}
            confirm = data.get('confirm', False)  # Требуем подтверждение
        
            if not confirm:
                return jsonify({'error': 'Confirmation required'}), 400
        
            from ....db.subscribers_db import get_subscription_by_id_only, get_subscription_servers, remove_subscription_server, DB_PATH
            import aiosqlite
        
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Проверяем существование подписки
                sub = loop.run_until_complete(get_subscription_by_id_only(sub_id))
                if not sub:
                    return jsonify({'error': 'Subscription not found'}), 404
            
                # Получаем все серверы подписки
                servers = loop.run_until_complete(get_subscription_servers(sub_id))
            
                # Получаем менеджеры
                def get_managers():
                    try:
                        from .... import bot as bot_module
                        return {
                            'subscription_manager': getattr(bot_module, 'subscription_manager', None),
                            'server_manager': getattr(bot_module, 'server_manager', None)
                        }
                    except (ImportError, AttributeError):
                        return {'subscription_manager': None, 'server_manager': None}
            
                managers = get_managers()
                server_manager = managers.get('server_manager')
            
                # 1. Удаляем клиентов со всех серверов
                async def delete_clients_from_servers():
                    deleted = []
                    failed = []
                    if server_manager and servers:
                        for server_info in servers:
                            server_name = server_info['server_name']
                            client_email = server_info['client_email']
                        
                            try:
                                xui, _ = server_manager.get_server_by_name(server_name)
                                if xui:
                                    # Используем run_in_executor для предотвращения блокировки
                                    import concurrent.futures
                                    loop = asyncio.get_event_loop()
                                    result = await loop.run_in_executor(
                                        None,
                                        lambda: xui.deleteClient(client_email, timeout=30)
                                    )
                                
                                    # Проверяем результат удаления
                                    if result is not None:
                                        status_code = getattr(result, 'status_code', None)
                                        if status_code == 200:
                                            deleted.append(server_name)
                                            logger.info(
                                                f"✅ Удален клиент {client_email} с сервера {server_name} "
                                                f"при удалении подписки {sub_id}"
                                            )
                                        else:
                                            failed.append(server_name)
                                            logger.warning(
                                                f"⚠️ Неожиданный статус код {status_code} при удалении "
                                                f"клиента {client_email} с сервера {server_name}"
                                            )
                                    else:
                                        failed.append(server_name)
                                        logger.warning(
                                            f"⚠️ Клиент {client_email} не найден на сервере {server_name} "
                                            f"(возможно, уже удален)"
                                        )
                                else:
                                    failed.append(server_name)
                                    logger.warning(f"Сервер {server_name} не найден в server_manager")
                            except Exception as e:
                                failed.append(server_name)
                                logger.error(
                                    f"❌ Ошибка удаления клиента {client_email} с сервера {server_name}: {e}",
                                    exc_info=True
                                )
                    return deleted, failed
            
                deleted_servers, failed_servers = loop.run_until_complete(delete_clients_from_servers())
            
                # 2. Удаляем связи подписки с серверами из БД
                for server_info in servers:
                    try:
                        loop.run_until_complete(remove_subscription_server(sub_id, server_info['server_name']))
                    except Exception as e:
                        logger.error(f"Ошибка удаления связи подписки {sub_id} с сервером {server_info['server_name']}: {e}")
            
                # 3. Удаляем подписку из БД
                async def delete_subscription():
                    async with aiosqlite.connect(DB_PATH) as db:
                        await db.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
                        await db.commit()
            
                loop.run_until_complete(delete_subscription())
            
                logger.info(f"Админ {admin_id} удалил подписку {sub_id}")
            finally:
                loop.close()
        
            return jsonify({
                'success': True,
                'message': 'Подписка удалена',
                'deleted_servers': deleted_servers,
                'failed_servers': failed_servers
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/subscription/delete: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500

    @bp.route('/api/admin/user/<user_id>/delete', methods=['POST', 'OPTIONS'])
    def api_admin_user_delete(user_id):
        """Полное удаление пользователя и всех связанных данных"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
    
        data = {}
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
        
            data = request.get_json(silent=True) or {}
            confirm = data.get('confirm', False)
        
            if not confirm:
                return jsonify({'error': 'Confirmation required'}), 400
        
            from ....db.subscribers_db import delete_user_completely, get_all_subscriptions_by_user, get_subscription_servers
            import aiosqlite
        
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Получаем все подписки пользователя для удаления клиентов с серверов
                all_subscriptions = loop.run_until_complete(get_all_subscriptions_by_user(user_id))
            
                # Получаем менеджеры
                def get_managers():
                    try:
                        from .... import bot as bot_module
                        return {
                            'server_manager': getattr(bot_module, 'server_manager', None)
                        }
                    except (ImportError, AttributeError):
                        return {'server_manager': None}
            
                managers = get_managers()
                server_manager = managers.get('server_manager')
            
                # Удаляем клиентов со всех серверов для всех подписок
                deleted_servers = []
                failed_servers = []
            
                async def delete_all_clients_from_servers():
                    deleted = []
                    failed = []
                
                    if server_manager and all_subscriptions:
                        for sub in all_subscriptions:
                            sub_id = sub['id']
                            servers = await get_subscription_servers(sub_id)
                        
                            for server_info in servers:
                                server_name = server_info['server_name']
                                client_email = server_info['client_email']
                            
                                try:
                                    xui, _ = server_manager.get_server_by_name(server_name)
                                    if xui:
                                        import concurrent.futures
                                        loop = asyncio.get_event_loop()
                                        result = await loop.run_in_executor(
                                            None,
                                            lambda: xui.deleteClient(client_email, timeout=30)
                                        )
                                    
                                        if result is not None:
                                            status_code = getattr(result, 'status_code', None)
                                            if status_code == 200:
                                                if server_name not in deleted:
                                                    deleted.append(server_name)
                                                logger.info(
                                                    f"✅ Удален клиент {client_email} с сервера {server_name} "
                                                    f"при удалении пользователя {user_id}"
                                                )
                                            else:
                                                if server_name not in failed:
                                                    failed.append(server_name)
                                                logger.warning(
                                                    f"⚠️ Неожиданный статус код {status_code} при удалении "
                                                    f"клиента {client_email} с сервера {server_name}"
                                                )
                                        else:
                                            if server_name not in failed:
                                                failed.append(server_name)
                                            logger.warning(
                                                f"⚠️ Клиент {client_email} не найден на сервере {server_name}"
                                            )
                                    else:
                                        if server_name not in failed:
                                            failed.append(server_name)
                                        logger.warning(f"Сервер {server_name} не найден в server_manager")
                                except Exception as e:
                                    if server_name not in failed:
                                        failed.append(server_name)
                                    logger.error(
                                        f"❌ Ошибка удаления клиента {client_email} с сервера {server_name}: {e}",
                                        exc_info=True
                                    )
                
                    return deleted, failed
            
                deleted_servers, failed_servers = loop.run_until_complete(delete_all_clients_from_servers())
            
                # Удаляем все данные пользователя из БД
                delete_stats = loop.run_until_complete(delete_user_completely(user_id))
            
                logger.info(f"Админ {admin_id} удалил пользователя {user_id}")
            finally:
                loop.close()
        
            return jsonify({
                'success': True,
                'stats': delete_stats,
                'deleted_servers': deleted_servers,
                'failed_servers': failed_servers
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/user/{user_id}/delete: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500

    @bp.route('/api/admin/stats', methods=['POST', 'OPTIONS'])
    def api_admin_stats():
        """Статистика для админ-панели"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
    
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
        
            # Попытка получить JSON безопасно
            try:
                data = request.get_json(silent=True) or {}
            except Exception as json_e:
                logger.warning(f"Ошибка парсинга JSON в /api/admin/stats: {json_e}")
                data = {}
        
            from ....db.subscribers_db import DB_PATH, get_subscription_statistics
            import aiosqlite
            import time
        
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Получаем статистику подписок
                stats = loop.run_until_complete(get_subscription_statistics())
            
                # Получаем общую статистику пользователей
                async def get_user_stats():
                    async with aiosqlite.connect(DB_PATH) as db:
                        db.row_factory = aiosqlite.Row
                        # Всего пользователей
                        async with db.execute("SELECT COUNT(*) as count FROM users") as cur:
                            row = await cur.fetchone()
                            total_users = row['count'] if row else 0
                    
                        # Пользователей за последние 30 дней
                        thirty_days_ago = int(time.time()) - (30 * 24 * 60 * 60)
                        async with db.execute(
                            "SELECT COUNT(*) as count FROM users WHERE first_seen >= ?",
                            (thirty_days_ago,)
                        ) as cur:
                            row = await cur.fetchone()
                            new_users_30d = row['count'] if row else 0
                    
                        return total_users, new_users_30d
            
                total_users, new_users_30d = loop.run_until_complete(get_user_stats())
            
                # Получаем статистику платежей
                async def get_payment_stats():
                    from ....db.payments_db import get_all_pending_payments
                    async with aiosqlite.connect(DB_PATH) as db:
                        db.row_factory = aiosqlite.Row
                        # Всего платежей
                        async with db.execute("SELECT COUNT(*) as count FROM payments") as cur:
                            row = await cur.fetchone()
                            total_payments = row['count'] if row else 0
                    
                        # Успешных платежей
                        async with db.execute(
                            "SELECT COUNT(*) as count FROM payments WHERE status = 'succeeded'"
                        ) as cur:
                            row = await cur.fetchone()
                            succeeded_payments = row['count'] if row else 0
                    
                        # Сумма успешных платежей (из meta)
                        async with db.execute(
                            "SELECT meta FROM payments WHERE status = 'succeeded'"
                        ) as cur:
                            rows = await cur.fetchall()
                            total_revenue = 0
                            for row in rows:
                                if row['meta']:
                                    try:
                                        import json
                                        meta = json.loads(row['meta']) if isinstance(row['meta'], str) else row['meta']
                                        # Пробуем получить amount или price
                                        amount = meta.get('amount') or meta.get('price', 0)
                                        if isinstance(amount, str):
                                            # Если это строка, пытаемся преобразовать
                                            try:
                                                amount = float(amount)
                                            except (ValueError, TypeError):
                                                amount = 0
                                        if isinstance(amount, (int, float)) and amount > 0:
                                            total_revenue += amount
                                    except Exception as e:
                                        logger.debug(f"Ошибка парсинга meta платежа для дохода: {e}")
                                        pass
                    
                        return total_payments, succeeded_payments, total_revenue
            
                total_payments, succeeded_payments, total_revenue = loop.run_until_complete(get_payment_stats())
            finally:
                loop.close()
        
            return jsonify({
                'success': True,
                'stats': {
                    'users': {
                        'total': total_users,
                        'new_30d': new_users_30d
                    },
                    'subscriptions': {
                        'total': stats.get('total', stats.get('total_subscriptions', 0)),
                        'active': stats.get('active', stats.get('active_subscriptions', 0)),
                        'expired': stats.get('expired', stats.get('expired_subscriptions', 0)),
                        'deleted': stats.get('deleted', stats.get('deleted_subscriptions', 0)),
                        'trial': stats.get('trial', 0)
                    },
                    'payments': {
                        'total': total_payments,
                        'succeeded': succeeded_payments,
                        'revenue': round(total_revenue, 2)
                    },
                    'business': {
                        'mrr': stats.get('mrr', 0),
                        'mrr_change': stats.get('mrr_change', 0),
                        'mrr_change_percent': stats.get('mrr_change_percent', 0)
                    }
                }
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/stats: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500

    @bp.route('/api/admin/charts/user-growth', methods=['POST', 'OPTIONS'])
    def api_admin_charts_user_growth():
        """Данные для графика роста пользователей"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
    
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
        
            data = request.get_json(silent=True) or {}
        
            days = int(data.get('days', 30))  # По умолчанию 30 дней
        
            from ....db.subscribers_db import get_user_growth_data
        
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                growth_data = loop.run_until_complete(get_user_growth_data(days))
            finally:
                loop.close()
        
            return jsonify({
                'success': True,
                'data': growth_data
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/charts/user-growth: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500

    @bp.route('/api/admin/charts/server-load', methods=['POST', 'OPTIONS'])
    def api_admin_charts_server_load():
        """Данные для графика нагрузки на серверы"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
    
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
        
            data = request.get_json(silent=True) or {}
        
            from ....db.subscribers_db import get_server_load_data
        
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                server_load_data = loop.run_until_complete(get_server_load_data())
                logger.info(f"Получены данные о нагрузке для {len(server_load_data)} серверов")
                if server_load_data:
                    logger.debug(f"Пример данных: {server_load_data[0]}")
            finally:
                loop.close()
        
            if not server_load_data:
                logger.warning("server_load_data пуст, возвращаем пустой ответ")
                return jsonify({
                    'success': True,
                    'data': {
                        'servers': [],
                        'locations': []
                    }
                }), 200, {
                    "Access-Control-Allow-Origin": "*",
                    "Content-Type": "application/json"
                }
        
            # Получаем информацию о серверах (display_name, location) из конфигурации
            def get_server_info():
                try:
                    from .... import bot as bot_module
                    server_manager = getattr(bot_module, 'server_manager', None)
                    if not server_manager:
                        return {}
                
                    server_info_map = {}
                    for location, servers in server_manager.servers_by_location.items():
                        for server in servers:
                            server_name = server['name']
                            display_name = server['config'].get('display_name', server_name)
                            server_info_map[server_name] = {
                                'display_name': display_name,
                                'location': location
                            }
                    return server_info_map
                except (ImportError, AttributeError):
                    return {}
        
            server_info_map = get_server_info()
        
            # Обогащаем данные информацией о серверах
            enriched_data = []
            for item in server_load_data:
                server_name = item['server_name']
                info = server_info_map.get(server_name, {})
                enriched_data.append({
                    'server_name': server_name,
                    'display_name': info.get('display_name', server_name),
                    'location': info.get('location', 'Unknown'),
                    'online_clients': item.get('online_clients', 0),
                    'total_active': item.get('total_active', 0),
                    'offline_clients': item.get('offline_clients', 0),
                    'avg_online_24h': item.get('avg_online_24h', 0),
                    'max_online_24h': item.get('max_online_24h', 0),
                    'min_online_24h': item.get('min_online_24h', 0),
                    'samples_24h': item.get('samples_24h', 0),
                    'load_percentage': item.get('load_percentage', 0)
                })
        
            # Группируем по локациям для дополнительной статистики
            location_stats = {}
            for item in enriched_data:
                location = item['location']
                if location not in location_stats:
                    location_stats[location] = {
                        'location': location,
                        'total_online': 0,
                        'total_active': 0,
                        'servers': []
                    }
                location_stats[location]['total_online'] += item['online_clients']
                location_stats[location]['total_active'] += item['total_active']
                location_stats[location]['servers'].append({
                    'server_name': item['server_name'],
                    'display_name': item['display_name'],
                    'online_clients': item['online_clients'],
                    'total_active': item['total_active']
                })
        
            return jsonify({
                'success': True,
                'data': {
                    'servers': enriched_data,
                    'locations': list(location_stats.values())
                }
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/charts/server-load: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500

    @bp.route('/api/admin/charts/conversion', methods=['POST', 'OPTIONS'])
    def api_admin_charts_conversion():
        """Данные для графика конверсии"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
    
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
        
            data = request.get_json(silent=True) or {}
        
            days = int(data.get('days', 30))  # По умолчанию 30 дней
        
            from ....db.subscribers_db import get_conversion_data
        
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                conversion_data = loop.run_until_complete(get_conversion_data(days))
            finally:
                loop.close()
        
            return jsonify({
                'success': True,
                'data': conversion_data
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/charts/conversion: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500

    @bp.route('/api/admin/charts/revenue-trend', methods=['POST', 'OPTIONS'])
    def api_admin_charts_revenue_trend():
        """Данные для графика динамики дохода"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
    
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
        
            data = request.get_json(silent=True) or {}
        
            days = int(data.get('days', 30))
        
            from ....db.subscribers_db import get_revenue_trend_data
        
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                revenue_data = loop.run_until_complete(get_revenue_trend_data(days))
            finally:
                loop.close()
        
            return jsonify({
                'success': True,
                'data': revenue_data
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/charts/revenue-trend: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500

    @bp.route('/api/admin/charts/notifications', methods=['POST', 'OPTIONS'])
    def api_admin_charts_notifications():
        """Данные для графиков уведомлений"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
    
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
        
            data = request.get_json(silent=True) or {}
        
            days = int(data.get('days', 7))  # По умолчанию 7 дней
        
            from ....db.notifications_db import get_notification_stats, get_daily_notification_stats
        
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Общая статистика
                stats = loop.run_until_complete(get_notification_stats(days))
            
                # Ежедневная статистика для графиков
                daily_stats = loop.run_until_complete(get_daily_notification_stats(days))
            
                # Формируем данные для графиков
                chart_data = {
                    'stats': {
                        'total_sent': stats.get('total_sent', 0),
                        'success_count': stats.get('success_count', 0),
                        'failed_count': stats.get('failed_count', 0),
                        'blocked_users': stats.get('blocked_users', 0),
                        'success_rate': stats.get('success_rate', 0),
                        'by_type': stats.get('by_type', [])
                    },
                    'daily': []
                }
            
                # Обрабатываем ежедневную статистику
                for day_stat in daily_stats:
                    date_str = day_stat.get('date', '')
                    total = day_stat.get('total', 0) or 0
                    success = day_stat.get('success', 0) or 0
                    failed = total - success
                
                    chart_data['daily'].append({
                        'date': date_str,
                        'total': total,
                        'success': success,
                        'failed': failed,
                        'success_rate': (success / total * 100) if total > 0 else 0
                    })
            
                # Сортируем по дате (от старых к новым)
                chart_data['daily'].sort(key=lambda x: x['date'])
            
            finally:
                loop.close()
        
            return jsonify({
                'success': True,
                'data': chart_data
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/charts/notifications: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500

    @bp.route('/api/admin/charts/subscriptions', methods=['POST', 'OPTIONS'])
    def api_admin_charts_subscriptions():
        """Данные для графиков подписок"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
    
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
        
            data = request.get_json(silent=True) or {}
        
            days = int(data.get('days', 30))
        
            # Импортируем функции из subscribers_db
            from ....db.subscribers_db import (
                get_subscription_types_statistics,
                get_subscription_dynamics_data,
                get_subscription_conversion_data
            )
        
            # Создаем новый event loop для async функций
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
            try:
                # Получаем статистику по типам
                types_stats = loop.run_until_complete(get_subscription_types_statistics())
            
                # Получаем динамику
                dynamics_data = loop.run_until_complete(get_subscription_dynamics_data(days))
            
                # Получаем данные конверсии
                conversion_data = loop.run_until_complete(get_subscription_conversion_data(days))
            
                # Рассчитываем конверсию
                total_trial = types_stats.get('trial_active', 0)
                total_purchased = types_stats.get('purchased_active', 0)
                total_active = types_stats.get('total_active', 0)
            
                # Конверсия = отношение активных купленных к активным пробным
                # Если есть пробные подписки, считаем процент купленных от пробных
                if total_trial > 0:
                    conversion_rate = (total_purchased / total_trial) * 100
                else:
                    # Если пробных нет, используем данные из conversion_data (историческая конверсия)
                    conversion_rate = conversion_data.get('conversion_rate', 0.0)
            
                result = {
                    'success': True,
                    'data': {
                        'types': {
                            'trial_active': types_stats.get('trial_active', 0),
                            'purchased_active': types_stats.get('purchased_active', 0),
                            'month_active': types_stats.get('month_active', 0),
                            '3month_active': types_stats.get('3month_active', 0),
                            'total_active': total_active,
                            'conversion_rate': round(conversion_rate, 2)
                        },
                        'dynamics': dynamics_data,
                        'conversion': conversion_data
                    }
                }
            
            finally:
                loop.close()
        
            return jsonify(result), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/charts/subscriptions: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500

    @bp.route('/api/admin/broadcast', methods=['POST', 'OPTIONS'])
    def api_admin_broadcast():
        """Отправка рассылки всем пользователям"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
    
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
        
            data = request.get_json(silent=True) or {}
        
            message_text = data.get('message', '').strip()
            if not message_text:
                return jsonify({'error': 'Message text is required'}), 400
        
            # Получаем список выбранных пользователей (опционально)
            user_ids = data.get('user_ids', [])
        
            # Импортируем необходимые модули
            from ....db import get_all_user_ids
            import telegram
        
            # Получаем список админов для исключения
            from .... import bot as bot_module
            ADMIN_IDS = getattr(bot_module, 'ADMIN_IDS', [])
            admin_set = set(str(a) for a in ADMIN_IDS)
        
            # Асинхронная функция для отправки рассылки
            async def send_broadcast_async():
                try:
                    # Если указаны конкретные пользователи - используем их, иначе всех
                    if user_ids and len(user_ids) > 0:
                        # Отправка только выбранным пользователям
                        recipients = [str(uid) for uid in user_ids if str(uid) not in admin_set]
                    else:
                        # Отправка всем пользователям
                        recipients = await get_all_user_ids()
                        recipients = [str(uid) for uid in recipients if str(uid) not in admin_set]
                
                    total = len(recipients)
                
                    if total == 0:
                        return {'sent': 0, 'failed': 0, 'total': 0}
                
                    sent = 0
                    failed = 0
                    batch = 40
                
                    # Создаем кнопку для открытия мини-приложения
                    from ....utils import UIButtons
                    webapp_button = UIButtons.create_webapp_button(text="Открыть в приложении")
                    reply_markup = None
                    if webapp_button:
                        from telegram import InlineKeyboardMarkup
                        reply_markup = InlineKeyboardMarkup([[webapp_button]])
                
                    # Получаем бот из приложения
                    bot = bot_app.bot
                    from ....db.subscribers_db import get_telegram_chat_id_for_notification
                
                    # Дедупликация по chat_id: один Telegram — одно сообщение
                    sent_chat_ids = set()
                    for i in range(0, total, batch):
                        chunk = recipients[i:i+batch]
                        for user_id in chunk:
                            chat_id = await get_telegram_chat_id_for_notification(user_id)
                            if chat_id is None:
                                continue
                            if chat_id in sent_chat_ids:
                                continue
                            sent_chat_ids.add(chat_id)
                            try:
                                await bot.send_message(
                                    chat_id=chat_id,
                                    text=message_text,
                                    parse_mode="HTML",
                                    disable_web_page_preview=True,
                                    reply_markup=reply_markup
                                )
                                sent += 1
                            except telegram.error.Forbidden:
                                failed += 1
                            except telegram.error.BadRequest:
                                failed += 1
                            except telegram.error.RetryAfter as e:
                                await asyncio.sleep(int(getattr(e, 'retry_after', 1)))
                                try:
                                    await bot.send_message(
                                        chat_id=chat_id,
                                        text=message_text,
                                        parse_mode="HTML",
                                        disable_web_page_preview=True,
                                        reply_markup=reply_markup
                                    )
                                    sent += 1
                                except Exception:
                                    failed += 1
                            except Exception as e:
                                logger.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")
                                failed += 1
                    
                        # Небольшая задержка между батчами для избежания rate limiting
                        if i + batch < total:
                            await asyncio.sleep(0.1)
                
                    return {'sent': sent, 'failed': failed, 'total': total}
                except Exception as e:
                    logger.error(f"Ошибка в send_broadcast_async: {e}", exc_info=True)
                    raise
        
            # Запускаем асинхронную функцию
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(send_broadcast_async())
                return jsonify(result), 200, {
                    "Access-Control-Allow-Origin": "*",
                    "Content-Type": "application/json"
                }
            finally:
                loop.close()
            
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/broadcast: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500

    @bp.route('/api/admin/server-groups', methods=['POST', 'OPTIONS'])
    def api_admin_server_groups():
        """Получение и добавление групп серверов"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
    
        data = {}
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
        
            data = request.get_json(silent=True) or {}
            from ....db.subscribers_db import get_server_groups, add_server_group, get_group_load_statistics
        
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                action = data.get('action', 'list')
                if action == 'list':
                    groups = loop.run_until_complete(get_server_groups(only_active=False))
                    stats = loop.run_until_complete(get_group_load_statistics())
                    return jsonify({'success': True, 'groups': groups, 'stats': stats})
                elif action == 'add':
                    name = data.get('name')
                    description = data.get('description')
                    is_default = data.get('is_default', False)
                    if not name:
                        return jsonify({'error': 'Name is required'}), 400
                    group_id = loop.run_until_complete(add_server_group(name, description, is_default))
                    return jsonify({'success': True, 'group_id': group_id})
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/server-groups: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/admin/server-group/update', methods=['POST', 'OPTIONS'])
    def api_admin_server_group_update():
        """Обновление группы серверов"""
        if request.method == 'OPTIONS': return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "*"})
    
        data = {}
        group_id = None
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
        
            data = request.get_json(silent=True) or {}
            group_id = data.get('id')
            if not group_id: return jsonify({'error': 'Group ID is required'}), 400
        
            from ....db.subscribers_db import update_server_group
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(update_server_group(
                    group_id, 
                    name=data.get('name'),
                    description=data.get('description'),
                    is_active=data.get('is_active'),
                    is_default=data.get('is_default')
                ))
                return jsonify({'success': True})
            finally:
                loop.close()
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/admin/servers-config', methods=['POST', 'OPTIONS'])
    def api_admin_servers_config():
        """Получение и добавление конфигурации серверов"""
        if request.method == 'OPTIONS': return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "*"})
    
        data = {}
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
        
            data = request.get_json(silent=True) or {}
            from ....db.subscribers_db import get_servers_config, add_server_config
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                action = data.get('action', 'list')
                if action == 'list':
                    group_id = data.get('group_id')
                    servers = loop.run_until_complete(get_servers_config(group_id=group_id, only_active=False))
                    return jsonify({'success': True, 'servers': servers})
                elif action == 'add':
                    group_id = data.get('group_id')
                    name = data.get('name')
                    host = data.get('host')
                    login = data.get('login')
                    password = data.get('password')
                    if not all([group_id, name, host, login, password]):
                        return jsonify({'error': 'All fields are required'}), 400
                    server_id = loop.run_until_complete(add_server_config(
                        group_id, name, host, login, password,
                        display_name=data.get('display_name'),
                        vpn_host=data.get('vpn_host'),
                        lat=data.get('lat'),
                        lng=data.get('lng'),
                        subscription_port=data.get('subscription_port'),
                        subscription_url=data.get('subscription_url') or None,
                        client_flow=data.get('client_flow') or None,
                        map_label=data.get('map_label') or None,
                        location=data.get('location') or None,
                        max_concurrent_clients=data.get('max_concurrent_clients')
                    ))
                
                    # Обновляем MultiServerManager
                    try:
                        from ....bot import server_manager, new_client_manager
                        from ....services.server_provider import ServerProvider
                        new_config = loop.run_until_complete(ServerProvider.get_all_servers_by_location())
                        if server_manager: server_manager.init_from_config(new_config)
                        if new_client_manager: new_client_manager.init_from_config(new_config)
                    except Exception as mgr_e:
                        logger.error(f"Ошибка обновления менеджера серверов: {mgr_e}")
                    
                    return jsonify({'success': True, 'server_id': server_id})
            finally:
                loop.close()
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/admin/server-config/update', methods=['POST', 'OPTIONS'])
    def api_admin_server_config_update():
        """Обновление конфигурации сервера"""
        if request.method == 'OPTIONS': return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "*"})
    
        data = {}
        server_id = None
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id): return jsonify({'error': 'Access denied'}), 403
        
            data = request.get_json(silent=True) or {}
            server_id = data.get('id')
            if not server_id: return jsonify({'error': 'Server ID is required'}), 400
        
            from ....db.subscribers_db import update_server_config, get_server_by_id
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Извлекаем все поля кроме initData и id
                update_data = {k: v for k, v in data.items() if k not in ['initData', 'id']}
                old_server = loop.run_until_complete(get_server_by_id(int(server_id)))
                old_flow = (old_server.get('client_flow') or '').strip() or None if old_server else None
                new_flow = (update_data.get('client_flow') or '').strip() or None
                client_flow_changed = (old_flow != new_flow)
            
                loop.run_until_complete(update_server_config(server_id, **update_data))
            
                # Обновляем MultiServerManager
                try:
                    from ....bot import server_manager, new_client_manager
                    from ....services.server_provider import ServerProvider
                    new_config = loop.run_until_complete(ServerProvider.get_all_servers_by_location())
                    if server_manager: server_manager.init_from_config(new_config)
                    if new_client_manager: new_client_manager.init_from_config(new_config)
                except Exception as mgr_e:
                    logger.error(f"Ошибка обновления менеджера серверов: {mgr_e}")
                
                return jsonify({'success': True, 'client_flow_changed': client_flow_changed, 'server_id': int(server_id)})
            finally:
                loop.close()
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/admin/server-config/sync-flow', methods=['POST', 'OPTIONS'])
    def api_admin_server_config_sync_flow():
        """Синхронизация flow у существующих клиентов на сервере после смены настройки client_flow"""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
            data = request.get_json(silent=True) or {}
            server_id = data.get('server_id') or data.get('id')
            if not server_id:
                return jsonify({'error': 'server_id is required'}), 400
            from ....db.subscribers_db import get_server_by_id
            from ....services.xui_service import X3
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                server = loop.run_until_complete(get_server_by_id(int(server_id)))
                if not server:
                    return jsonify({'error': 'Server not found'}), 404
                x3 = X3(
                    login=server['login'],
                    password=server['password'],
                    host=server['host'],
                    vpn_host=server.get('vpn_host'),
                    subscription_port=server.get('subscription_port', 2096),
                    subscription_url=server.get('subscription_url')
                )
                flow_val = (server.get('client_flow') or '').strip() or ''
                updated, errs = x3.sync_flow_for_all_clients(flow_val)
                return jsonify({
                    'success': True,
                    'updated': updated,
                    'errors': errs[:20]
                })
            finally:
                loop.close()
        except Exception as e:
            logger.exception("sync-flow error")
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/admin/server-config/delete', methods=['POST', 'OPTIONS'])
    def api_admin_server_config_delete():
        """Удаление конфигурации сервера"""
        if request.method == 'OPTIONS': return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "*"})
    
        data = {}
        server_id = None
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id): return jsonify({'error': 'Access denied'}), 403
        
            data = request.get_json(silent=True) or {}
            server_id = data.get('id')
            if not server_id: return jsonify({'error': 'Server ID is required'}), 400
        
            from ....db.subscribers_db import delete_server_config
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(delete_server_config(server_id))
                return jsonify({'success': True})
            finally:
                loop.close()
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/admin/sync-all', methods=['POST', 'OPTIONS'])
    def api_admin_sync_all():
        """Полная синхронизация всех серверов"""
        if request.method == 'OPTIONS': return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
        
            from ....bot import sync_manager
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                stats = loop.run_until_complete(sync_manager.sync_all_subscriptions(auto_fix=True))
                return jsonify({'success': True, 'stats': stats})
            finally:
                loop.close()
        except Exception as e:
            return jsonify({'error': str(e)}), 500


    return bp
