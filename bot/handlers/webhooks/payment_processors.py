"""
Обработчики платежей из webhook'ов YooKassa
"""
import logging
import json
import datetime
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

from ...db import get_payment_by_id, update_payment_status, update_payment_activation
from ...utils import (
    UIEmojis, UIStyles, UIMessages,
    safe_edit_message_with_photo, safe_send_message_with_photo,
    format_vpn_key_message
)
from ...navigation import NavigationBuilder, CallbackData

logger = logging.getLogger(__name__)


def get_globals():
    """Получает глобальные переменные из bot.py"""
    try:
        from ... import bot as bot_module
        return {
            'server_manager': getattr(bot_module, 'server_manager', None),
            'new_client_manager': getattr(bot_module, 'new_client_manager', None),
            'notification_manager': getattr(bot_module, 'notification_manager', None),
            'subscription_manager': getattr(bot_module, 'subscription_manager', None),
        }
    except (ImportError, AttributeError):
        return {
            'server_manager': None,
            'new_client_manager': None,
            'notification_manager': None,
            'subscription_manager': None,
        }


async def process_payment_webhook(bot_app, payment_id, status):
    """Обрабатывает платеж из webhook'а"""
    try:
        # Получаем информацию о платеже из базы данных
        payment_info = await get_payment_by_id(payment_id)
        if not payment_info:
            logger.warning(f"Платеж {payment_id} не найден в базе данных")
            return
        
        # Проверяем, не обработан ли уже этот платеж
        current_status = payment_info.get('status', 'pending')
        is_activated = payment_info.get('activated', 0)
        
        if status == 'succeeded' and current_status == 'succeeded' and is_activated == 1:
            logger.info(f"Платеж {payment_id} уже обработан, пропускаем повторную обработку")
            return
        
        user_id = payment_info['user_id']
        meta = payment_info['meta'] if isinstance(payment_info['meta'], dict) else json.loads(payment_info['meta'])
        
        logger.info(f"Обработка webhook платежа: payment_id={payment_id}, user_id={user_id}, status={status}, current_status={current_status}, activated={is_activated}")
        
        # Обрабатываем платеж аналогично auto_activate_keys
        if status == 'succeeded':
            # Успешная оплата - обрабатываем как в auto_activate_keys
            await process_successful_payment(bot_app, payment_id, user_id, meta)
        elif status in ['canceled', 'refunded']:
            # Отмененная/возвращенная оплата
            await process_canceled_payment(bot_app, payment_id, user_id, meta, status)
        elif status not in ['pending']:
            # Любой другой неуспешный статус
            await process_failed_payment(bot_app, payment_id, user_id, meta, status)
        
    except Exception as e:
        logger.error(f"Ошибка обработки webhook платежа {payment_id}: {e}")


async def process_successful_payment(bot_app, payment_id, user_id, meta):
    """Обрабатывает успешный платеж"""
    try:
        period = meta.get('type', 'month')
        device_limit = int(meta.get('device_limit', 1))
        # Получаем message_id из мета-данных платежа
        message_id = meta.get('message_id')
        
        # Проверяем, это продление или новая покупка
        is_extension = period.startswith('extend_')
        if is_extension:
            # Обработка продления (код из auto_activate_keys)
            await process_extension_payment(bot_app, payment_id, user_id, meta, message_id)
        else:
            # Обработка новой покупки (код из auto_activate_keys)
            await process_new_purchase_payment(bot_app, payment_id, user_id, meta, message_id)
            
    except Exception as e:
        logger.error(f"Ошибка обработки успешного платежа {payment_id}: {e}")


async def process_extension_payment(bot_app, payment_id, user_id, meta, message_id):
    """Обрабатывает продление ключа или подписки"""
    try:
        period = meta.get('type', 'month')
        actual_period = period.replace('extend_', '').replace('extend_sub_', '')  # убираем префиксы
        days = 90 if actual_period == '3month' else 30
        
        # Проверяем, это продление подписки или старого ключа
        is_subscription_extension = period.startswith('extend_sub_')
        extension_subscription_id = meta.get('extension_subscription_id')
        extension_email = meta.get('extension_key_email')
        
        if is_subscription_extension:
            # Продление подписки
            logger.info(f"Обработка продления подписки: subscription_id={extension_subscription_id}, period={actual_period}, days={days}")
            
            if not extension_subscription_id:
                logger.error(f"Не найден subscription_id для продления в meta: {meta}")
                await update_payment_status(payment_id, 'failed')
                return
            
            # Получаем глобальные переменные
            globals_dict = get_globals()
            subscription_manager = globals_dict.get('subscription_manager')
            new_client_manager = globals_dict.get('new_client_manager')
            
            if not subscription_manager or not new_client_manager:
                logger.error("subscription_manager или new_client_manager не доступен")
                await update_payment_status(payment_id, 'failed')
                return
            
            # Получаем информацию о подписке
            from ...db.subscribers_db import get_subscription_servers
            servers = await get_subscription_servers(extension_subscription_id)
            
            if not servers:
                logger.error(f"Не найдены серверы для подписки {extension_subscription_id}")
                await update_payment_status(payment_id, 'failed')
                return
            
            # Продлеваем ключи на всех серверах подписки
            successful_extensions = []
            failed_extensions = []
            
            for server_info in servers:
                server_name = server_info['server_name']
                client_email = server_info['client_email']
                
                try:
                    xui, resolved_name = new_client_manager.get_server_by_name(server_name)
                    if not xui:
                        logger.warning(f"Сервер {server_name} недоступен для продления")
                        failed_extensions.append(server_name)
                        continue
                    
                    response = xui.extendClient(client_email, days)
                    
                    # Проверяем не только HTTP статус, но и поле success в JSON
                    is_success = False
                    if response and response.status_code == 200:
                        try:
                            response_json = response.json()
                            is_success = response_json.get('success', False)
                            if not is_success:
                                error_msg = response_json.get('msg', 'Unknown error')
                                logger.warning(f"Не удалось продлить ключ на сервере {server_name}: {error_msg}")
                        except (json.JSONDecodeError, ValueError):
                            # Если ответ не JSON, считаем успешным только если статус 200
                            is_success = True
                            logger.warning(f"Ответ от {server_name} не является валидным JSON, но статус 200")
                    
                    if is_success:
                        successful_extensions.append(server_name)
                        logger.info(f"Ключ продлен на сервере {server_name} для подписки {extension_subscription_id}")
                    else:
                        logger.warning(f"Не удалось продлить ключ на сервере {server_name}: статус {response.status_code if response else 'None'}")
                        failed_extensions.append(server_name)
                except Exception as e:
                    logger.error(f"Ошибка продления ключа на сервере {server_name}: {e}")
                    failed_extensions.append(server_name)
            
            if not successful_extensions:
                logger.error(f"Не удалось продлить ключи ни на одном сервере для подписки {extension_subscription_id}")
                await update_payment_status(payment_id, 'failed')
                # Уведомляем пользователя
                if message_id:
                    error_message = (
                        f"{UIStyles.header('Ошибка продления подписки')}\n\n"
                        f"{UIEmojis.ERROR} <b>Не удалось продлить подписку!</b>\n\n"
                        f"<b>Причина:</b> Не удалось продлить ключи на серверах\n\n"
                        f"{UIStyles.description('Попробуйте позже или обратитесь в поддержку')}"
                    )
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("Попробовать снова", callback_data=CallbackData.MYKEYS_MENU)],
                        [NavigationBuilder.create_main_menu_button()]
                    ])
                    await safe_edit_message_with_photo(
                        bot_app.bot,
                        chat_id=int(user_id),
                        message_id=message_id,
                        text=error_message,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        menu_type='extend_key'
                    )
                return
            
            # Обновляем срок действия подписки в БД
            import time
            from ...db.subscribers_db import get_active_subscription_by_user
            sub = await get_active_subscription_by_user(str(user_id))
            if sub and sub['id'] == extension_subscription_id:
                # Вычисляем новое время истечения
                current_expires_at = sub['expires_at']
                current_time = int(time.time())
                # Если подписка уже истекла, начинаем с текущего времени, иначе продлеваем от текущего expires_at
                base_time = max(current_expires_at, current_time)
                new_expires_at = base_time + days * 24 * 60 * 60
                
                # Обновляем expires_at в БД
                from ...db.subscribers_db import update_subscription_expiry
                await update_subscription_expiry(extension_subscription_id, new_expires_at)
                logger.info(f"Подписка {extension_subscription_id} продлена до {new_expires_at}")
            
            await update_payment_status(payment_id, 'succeeded')
            await update_payment_activation(payment_id, 1)
            
            # Отправляем уведомление о продлении подписки
            try:
                expiry_time = datetime.datetime.fromtimestamp(new_expires_at)
                expiry_str = expiry_time.strftime('%d.%m.%Y %H:%M')
                period_text = "3 месяца" if actual_period == "3month" else "1 месяц"
                
                extension_message = (
                    f"{UIStyles.header('Подписка продлена!')}\n\n"
                    f"{UIEmojis.SUCCESS} <b>Ваша подписка успешно продлена</b>\n\n"
                    f"<b>Период:</b> {period_text}\n"
                    f"<b>Новое окончание:</b> {expiry_str}\n"
                    f"<b>Серверов продлено:</b> {len(successful_extensions)}\n\n"
                )
                
                if failed_extensions:
                    extension_message += f"{UIEmojis.WARNING} <i>Не удалось продлить на серверах: {', '.join(failed_extensions)}</i>\n\n"
                
                extension_message += f"{UIStyles.description('Подписка активна и готова к использованию.')}"
                
                if message_id:
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("Мои ключи", callback_data=CallbackData.MYKEYS_MENU)],
                        [NavigationBuilder.create_main_menu_button()]
                    ])
                    
                    await safe_edit_message_with_photo(
                        bot_app.bot,
                        chat_id=int(user_id),
                        message_id=message_id,
                        text=extension_message,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        menu_type='extend_key'
                    )
                    logger.info(f"Отредактировано сообщение о продлении подписки {extension_subscription_id} пользователю {user_id}")
                else:
                    # Fallback: отправляем новое сообщение
                    await safe_send_message_with_photo(
                        bot_app.bot,
                        chat_id=int(user_id),
                        text=extension_message,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        menu_type='extend_key'
                    )
                    logger.info(f"Отправлено новое сообщение о продлении подписки {extension_subscription_id} пользователю {user_id}")
                    
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления о продлении подписки: {e}")
            
            return
        
        # Продление старого ключа (legacy)
        logger.info(f"Обработка продления ключа: email={extension_email}, period={actual_period}, days={days}")
        
        if not extension_email:
            logger.error(f"Не найден email ключа для продления в meta: {meta}")
            await update_payment_status(payment_id, 'failed')
            return
        
        # Получаем глобальные переменные
        globals_dict = get_globals()
        server_manager = globals_dict['server_manager']
        notification_manager = globals_dict['notification_manager']
        
        if not server_manager:
            logger.error("server_manager не доступен")
            await update_payment_status(payment_id, 'failed')
            return
        
        # Ищем сервер с ключом для продления
        try:
            xui, server_name = server_manager.find_client_on_any_server(extension_email)
            if not xui or not server_name:
                logger.error(f"Ключ для продления не найден: {extension_email}")
                await update_payment_status(payment_id, 'failed')
                
                # Отправляем сообщение пользователю об ошибке продления
                if message_id:
                    error_message = (
                        f"{UIStyles.header('Ошибка продления')}\n\n"
                        f"{UIEmojis.ERROR} <b>Не удалось продлить ключ!</b>\n\n"
                        f"<b>Ключ:</b> {extension_email}\n"
                        f"<b>Причина:</b> Ключ не найден на сервере\n\n"
                        f"{UIStyles.description('Попробуйте продлить заново или обратитесь в поддержку')}"
                    )
                    
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("Попробовать снова", callback_data=CallbackData.MYKEYS_MENU)],
                        [NavigationBuilder.create_main_menu_button()]
                    ])
                    
                    await safe_edit_message_with_photo(
                        bot_app.bot,
                        chat_id=int(user_id),
                        message_id=message_id,
                        text=error_message,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        menu_type='extend_key'
                    )
                return
            
            # Продлеваем ключ
            try:
                response = xui.extendClient(extension_email, days)
            except Exception as e:
                logger.error(f"Ошибка при продлении ключа {extension_email} на сервере {server_name}: {e}")
                await update_payment_status(payment_id, 'failed')
                # Отправляем сообщение об ошибке пользователю
                if message_id:
                    error_message = (
                        f"{UIStyles.header('Ошибка продления')}\n\n"
                        f"{UIEmojis.ERROR} <b>Не удалось продлить ключ!</b>\n\n"
                        f"<b>Ключ:</b> {extension_email}\n"
                        f"<b>Причина:</b> Сервер временно недоступен\n\n"
                        f"{UIStyles.description('Попробуйте позже или обратитесь в поддержку')}"
                    )
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("Попробовать снова", callback_data=CallbackData.MYKEYS_MENU)],
                        [NavigationBuilder.create_main_menu_button()]
                    ])
                    try:
                        await safe_edit_message_with_photo(
                            bot_app.bot,
                            chat_id=int(user_id),
                            message_id=message_id,
                            text=error_message,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            menu_type='extend_key'
                        )
                    except Exception as edit_e:
                        logger.error(f"Ошибка отправки сообщения об ошибке: {edit_e}")
                return
            
            # Проверяем не только HTTP статус, но и поле success в JSON
            is_success = False
            if response and response.status_code == 200:
                try:
                    response_json = response.json()
                    is_success = response_json.get('success', False)
                    if not is_success:
                        error_msg = response_json.get('msg', 'Unknown error')
                        logger.error(f"Не удалось продлить ключ {extension_email}: {error_msg}")
                        await update_payment_status(payment_id, 'failed')
                        # Отправляем сообщение об ошибке пользователю
                        if message_id:
                            error_message = (
                                f"{UIStyles.header('Ошибка продления')}\n\n"
                                f"{UIEmojis.ERROR} <b>Не удалось продлить ключ!</b>\n\n"
                                f"<b>Ключ:</b> {extension_email}\n"
                                f"<b>Причина:</b> {error_msg}\n\n"
                                f"{UIStyles.description('Попробуйте позже или обратитесь в поддержку')}"
                            )
                            keyboard = InlineKeyboardMarkup([
                                [InlineKeyboardButton("Попробовать снова", callback_data=CallbackData.MYKEYS_MENU)],
                                [NavigationBuilder.create_main_menu_button()]
                            ])
                            try:
                                await safe_edit_message_with_photo(
                                    bot_app.bot,
                                    chat_id=int(user_id),
                                    message_id=message_id,
                                    text=error_message,
                                    reply_markup=keyboard,
                                    parse_mode="HTML",
                                    menu_type='extend_key'
                                )
                            except Exception as edit_e:
                                logger.error(f"Ошибка отправки сообщения об ошибке: {edit_e}")
                        return
                except (json.JSONDecodeError, ValueError):
                    # Если ответ не JSON, считаем успешным только если статус 200
                    is_success = True
                    logger.warning(f"Ответ от {server_name} не является валидным JSON, но статус 200")
            
            if is_success:
                await update_payment_status(payment_id, 'succeeded')
                await update_payment_activation(payment_id, 1)
                
                # Отправляем уведомление о продлении
                try:
                    # Получаем новое время истечения
                    try:
                        clients_response = xui.list()
                    except Exception as e:
                        logger.error(f"Ошибка получения списка клиентов после продления: {e}")
                        clients_response = {}
                    expiry_str = "—"
                    if clients_response.get('success', False):
                        for inbound in clients_response.get('obj', []):
                            settings = json.loads(inbound.get('settings', '{}'))
                            for client in settings.get('clients', []):
                                if client.get('email') == extension_email:
                                    expiry_timestamp = int(client.get('expiryTime', 0) / 1000)
                                    expiry_str = datetime.datetime.fromtimestamp(expiry_timestamp).strftime('%d.%m.%Y %H:%M') if expiry_timestamp else '—'
                                    break
                    
                    # Очищаем старые уведомления об истечении для продленного ключа
                    if notification_manager:
                        await notification_manager.clear_key_notifications(user_id, extension_email)
                        await notification_manager.record_key_extension(user_id, extension_email)
                    
                    extension_message = UIMessages.key_extended_message(
                        email=extension_email,
                        server_name=server_name,
                        days=days,
                        expiry_str=expiry_str,
                        period=actual_period
                    )
                    
                    if message_id:
                        keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton("Мои ключи", callback_data=CallbackData.MYKEYS_MENU)],
                            [NavigationBuilder.create_main_menu_button()]
                        ])
                        
                        await safe_edit_message_with_photo(
                            bot_app.bot,
                            chat_id=int(user_id),
                            message_id=message_id,
                            text=extension_message,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            menu_type='extend_key'
                        )
                        logger.info(f"Отредактировано сообщение о продлении ключа {extension_email} пользователю {user_id}")
                    else:
                        # Fallback: отправляем новое сообщение
                        await safe_send_message_with_photo(
                            bot_app.bot,
                            chat_id=int(user_id),
                            text=extension_message,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            menu_type='extend_key'
                        )
                        logger.info(f"Отправлено новое сообщение о продлении ключа {extension_email} пользователю {user_id}")
                    
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления о продлении: {e}")
            else:
                logger.error(f"Ошибка продления ключа {extension_email}: {response}")
                await update_payment_status(payment_id, 'failed')
                
        except Exception as e:
            logger.error(f"Ошибка при продлении ключа {extension_email}: {e}")
            await update_payment_status(payment_id, 'failed')
                    
    except Exception as e:
        logger.error(f"Ошибка обработки продления ключа {payment_id}: {e}")


async def process_new_purchase_payment(bot_app, payment_id, user_id, meta, message_id):
    """Обрабатывает новую покупку - создаёт подписку и ключи на всех доступных серверах"""
    try:
        period = meta.get('type', 'month')
        days = 90 if period == '3month' else 30
        device_limit = int(meta.get('device_limit', 1))
        unique_email = meta.get('unique_email')
        
        logger.info(f"Обработка новой покупки: period={period}, days={days}, email={unique_email}")
        
        if not unique_email:
            logger.error(f"Не найден unique_email в meta: {meta}")
            await update_payment_status(payment_id, 'failed')
            return
        
        # Получаем глобальные переменные
        globals_dict = get_globals()
        new_client_manager = globals_dict['new_client_manager']
        subscription_manager = globals_dict.get('subscription_manager')
        
        if not new_client_manager:
            logger.error("new_client_manager не доступен")
            await update_payment_status(payment_id, 'failed')
            return
        
        if not subscription_manager:
            logger.error("subscription_manager не доступен")
            await update_payment_status(payment_id, 'failed')
            return
        
        # Шаг 1: Создаём подписку в БД (Saga Pattern: сначала БД, потом внешние системы)
        # Это гарантирует, что у нас есть запись в БД даже если создание на серверах не удастся
        price = float(meta.get('price', '0') or 0)
        sub_dict = None
        token = None
        subscription_created = False
        try:
            sub_dict, token = await subscription_manager.create_subscription_for_user(
                user_id=str(user_id),
                period=period,
                device_limit=device_limit,
                price=price,
            )
            subscription_created = True
            logger.info(f"Подписка создана: sub_id={sub_dict['id']}, token={token}")
        except Exception as sub_e:
            logger.error(f"Ошибка при создании подписки для user_id={user_id}: {sub_e}")
            await update_payment_status(payment_id, 'failed')
            return
        
        # Шаг 2: Получаем все доступные серверы
        all_health = new_client_manager.check_all_servers_health(force_check=False)
        healthy_servers = []
        for server in new_client_manager.servers:
            server_name = server["name"]
            if all_health.get(server_name, False) and server.get("x3") is not None:
                healthy_servers.append((server["x3"], server_name))
        
        if not healthy_servers:
            logger.error("Нет доступных серверов для создания ключей")
            await update_payment_status(payment_id, 'failed')
            # Уведомляем пользователя
            try:
                error_message = (
                    f"{UIStyles.header('Ошибка создания подписки')}\n\n"
                    f"{UIEmojis.ERROR} <b>Не удалось создать подписку!</b>\n\n"
                    f"<b>Причина:</b> Все серверы временно недоступны\n\n"
                    f"{UIStyles.description('Попробуйте позже или обратитесь в поддержку')}"
                )
                keyboard = InlineKeyboardMarkup([
                    [NavigationBuilder.create_main_menu_button()]
                ])
                await safe_edit_message_with_photo(
                    bot_app.bot,
                    chat_id=int(user_id),
                    message_id=message_id,
                    text=error_message,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    menu_type='payment'
                )
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения об ошибке: {e}")
            return
        
        # Шаг 3: Создаём клиента на каждом доступном сервере с одним и тем же email
        # Используем токен подписки как subId для связи клиента с подпиской в X-UI
        successful_servers = []
        failed_servers = []
        
        for xui, server_name in healthy_servers:
            try:
                # Проверяем, не существует ли уже клиент на сервере (предотвращение рассинхронизации)
                client_already_exists = False
                try:
                    if xui.client_exists(unique_email):
                        logger.info(f"Клиент с email {unique_email} уже существует на сервере {server_name}, пропускаем создание")
                        client_already_exists = True
                        is_success = True
                    else:
                        # Клиент не существует, создаем его
                        response = xui.addClient(
                            day=days, 
                            tg_id=user_id, 
                            user_email=unique_email, 
                            timeout=15,
                            key_name=token  # Используем токен подписки как subId
                        )
                        
                        # Проверяем не только HTTP статус, но и поле success в JSON
                        is_success = False
                        if response.status_code == 200:
                            try:
                                response_json = response.json()
                                is_success = response_json.get('success', False)
                                if not is_success:
                                    error_msg = response_json.get('msg', 'Unknown error')
                                    # Проверяем, не является ли ошибка "Duplicate email" - это означает, что клиент уже существует
                                    if 'duplicate email' in error_msg.lower() or 'duplicate' in error_msg.lower():
                                        logger.info(f"Клиент с email {unique_email} уже существует на сервере {server_name}, считаем успехом")
                                        is_success = True
                                        client_already_exists = True
                                    else:
                                        logger.warning(f"Не удалось создать клиента на сервере {server_name}: {error_msg}")
                            except (json.JSONDecodeError, ValueError):
                                # Если ответ не JSON, считаем успешным только если статус 200
                                is_success = True
                                logger.warning(f"Ответ от {server_name} не является валидным JSON, но статус 200")
                except Exception as check_e:
                    # Если проверка существования не удалась, все равно пытаемся создать
                    logger.warning(f"Ошибка проверки существования клиента на {server_name}: {check_e}, пытаемся создать")
                    response = xui.addClient(
                        day=days, 
                        tg_id=user_id, 
                        user_email=unique_email, 
                        timeout=15,
                        key_name=token
                    )
                    
                    is_success = False
                    if response.status_code == 200:
                        try:
                            response_json = response.json()
                            is_success = response_json.get('success', False)
                            if not is_success:
                                error_msg = response_json.get('msg', 'Unknown error')
                                if 'duplicate email' in error_msg.lower() or 'duplicate' in error_msg.lower():
                                    logger.info(f"Клиент с email {unique_email} уже существует на сервере {server_name}")
                                    is_success = True
                                    client_already_exists = True
                                else:
                                    logger.warning(f"Не удалось создать клиента на сервере {server_name}: {error_msg}")
                        except (json.JSONDecodeError, ValueError):
                            is_success = True
                            logger.warning(f"Ответ от {server_name} не является валидным JSON, но статус 200")
                
                if is_success:
                    successful_servers.append((server_name, unique_email))
                    # Привязываем сервер к подписке
                    try:
                        await subscription_manager.attach_server_to_subscription(
                            subscription_id=sub_dict["id"],
                            server_name=server_name,
                            client_email=unique_email,
                            client_id=None,
                        )
                        logger.info(f"Клиент создан и привязан к подписке на сервере {server_name}")
                    except Exception as attach_e:
                        logger.error(f"Ошибка привязки сервера {server_name} к подписке: {attach_e}")
                else:
                    logger.warning(f"Не удалось создать клиента на сервере {server_name}: статус {response.status_code}")
                    failed_servers.append(server_name)
            except Exception as e:
                logger.error(f"Ошибка создания клиента на сервере {server_name}: {e}")
                failed_servers.append(server_name)
        
        if not successful_servers:
            logger.error("Не удалось создать клиента ни на одном сервере")
            
            # Компенсирующая транзакция (Saga Pattern): откатываем создание подписки в БД
            if subscription_created and sub_dict:
                try:
                    from ...db.subscribers_db import update_subscription_status
                    await update_subscription_status(sub_dict['id'], 'canceled')
                    logger.info(f"Подписка {sub_dict['id']} отменена из-за ошибки создания клиентов (компенсирующая транзакция)")
                except Exception as rollback_e:
                    logger.error(f"Ошибка отката подписки {sub_dict['id']}: {rollback_e}")
            
            await update_payment_status(payment_id, 'failed')
            # Уведомляем пользователя
            try:
                error_message = (
                    f"{UIStyles.header('Ошибка создания подписки')}\n\n"
                    f"{UIEmojis.ERROR} <b>Не удалось создать подписку!</b>\n\n"
                    f"<b>Причина:</b> Не удалось создать ключи на серверах\n\n"
                    f"{UIStyles.description('Попробуйте позже или обратитесь в поддержку')}"
                )
                keyboard = InlineKeyboardMarkup([
                    [NavigationBuilder.create_main_menu_button()]
                ])
                await safe_edit_message_with_photo(
                    bot_app.bot,
                    chat_id=int(user_id),
                    message_id=message_id,
                    text=error_message,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    menu_type='payment'
                )
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения об ошибке: {e}")
            return
        
        # Шаг 4: Обновляем статус платежа
        await update_payment_status(payment_id, 'succeeded')
        await update_payment_activation(payment_id, 1)
        
        # Шаг 5: Отправляем информацию о подписке пользователю
        try:
            # Вычисляем время истечения
            expiry_time = datetime.datetime.now() + datetime.timedelta(days=days)
            expiry_str = expiry_time.strftime('%d.%m.%Y %H:%M')
            expiry_timestamp = int(expiry_time.timestamp())
            
            # Получаем WEBHOOK_URL для формирования полного URL подписки
            # WEBHOOK_URL должен быть публичным URL вашего webhook сервера (например, через ngrok или домен)
            # Формат: http://your-domain.com или https://your-domain.com
            import os
            webhook_url = os.getenv("WEBHOOK_URL", "").rstrip("/")
            
            # Формируем subscription URL
            if webhook_url:
                # Используем публичный URL webhook сервера
                subscription_url = f"{webhook_url}/sub/{token}"
                logger.info(f"Subscription URL сформирован: {subscription_url}")
            else:
                # Если WEBHOOK_URL не установлен, предупреждаем
                # В продакшене это должно быть обязательно установлено!
                subscription_url = f"http://localhost:5000/sub/{token}"  # Временный fallback для разработки
                logger.warning(
                    "⚠️ WEBHOOK_URL не установлен! "
                    "Установите переменную окружения WEBHOOK_URL с публичным URL вашего webhook сервера. "
                    "Например: WEBHOOK_URL=https://your-domain.com или через ngrok: WEBHOOK_URL=https://xxxx.ngrok.io"
                )
            
            # Формируем сообщение о подписке
            period_text = "3 месяца" if period == "3month" else "1 месяц"
            subscription_message = (
                f"{UIStyles.header('Подписка активирована!')}\n\n"
                f"{UIEmojis.SUCCESS} <b>Ваша подписка успешно создана</b>\n\n"
                f"<b>Период:</b> {period_text}\n"
                f"<b>Окончание:</b> {expiry_str}\n"
                f"<b>Серверов:</b> {len(successful_servers)}\n"
                f"<b>Устройств:</b> {device_limit}\n\n"
                f"{UIStyles.subheader('Ссылка на подписку:')}\n"
                f"<code>{subscription_url}</code>\n\n"
                f"{UIStyles.description('Используйте эту ссылку для импорта в VPN-клиент. Подписка включает все доступные серверы.')}"
            )
            
            if failed_servers:
                subscription_message += f"\n\n{UIEmojis.WARNING} <i>Не удалось создать ключи на серверах: {', '.join(failed_servers)}</i>"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Мои ключи", callback_data="mykeys_menu")],
                [NavigationBuilder.create_main_menu_button()]
            ])
            
            # Получаем message_id из мета-данных платежа
            payment_info = await get_payment_by_id(payment_id)
            stored_message_id = None
            if payment_info and payment_info.get('meta'):
                if isinstance(payment_info['meta'], dict):
                    stored_message_id = payment_info['meta'].get('message_id')
                elif isinstance(payment_info['meta'], str):
                    try:
                        meta_dict = json.loads(payment_info['meta'])
                        stored_message_id = meta_dict.get('message_id')
                    except:
                        pass
            
            # Используем message_id из webhook или из базы данных
            actual_message_id = message_id or stored_message_id
            
            if actual_message_id:
                try:
                    await safe_edit_message_with_photo(
                        bot_app.bot,
                        chat_id=int(user_id),
                        message_id=actual_message_id,
                        text=subscription_message,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        menu_type='key_success'
                    )
                    logger.info(f"Отредактировано сообщение с оплатой {actual_message_id} на информацию о подписке")
                except Exception as edit_error:
                    # Игнорируем ошибки "no text" - это нормально, если сообщение уже отредактировано как медиа
                    error_str = str(edit_error).lower()
                    if "no text" in error_str or "can't be edited" in error_str:
                        logger.debug(f"Сообщение {actual_message_id} уже отредактировано как медиа, пропускаем: {edit_error}")
                    else:
                        logger.error(f"Ошибка редактирования сообщения {actual_message_id}: {edit_error}")
                    # Fallback: отправляем новое сообщение
                    await safe_send_message_with_photo(
                        bot_app.bot,
                        chat_id=int(user_id),
                        text=subscription_message,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        menu_type='key_success'
                    )
                    logger.info(f"Отправлено новое сообщение с подпиской для user_id={user_id}")
            else:
                # Если нет message_id, отправляем новое сообщение
                await safe_send_message_with_photo(
                    bot_app.bot,
                    chat_id=int(user_id),
                    text=subscription_message,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    menu_type='key_success'
                )
                logger.info(f"Отправлено новое сообщение с подпиской для user_id={user_id}")
                
        except Exception as e:
            logger.error(f"Ошибка отправки информации о подписке пользователю: {e}")
            
    except Exception as e:
        logger.error(f"Ошибка обработки новой покупки {payment_id}: {e}")
        await update_payment_status(payment_id, 'failed')


async def process_canceled_payment(bot_app, payment_id, user_id, meta, status):
    """Обрабатывает отмененный платеж"""
    try:
        await update_payment_status(payment_id, 'failed')
        await update_payment_activation(payment_id, 0)
        
        # Отправляем сообщение пользователю об ошибке оплаты
        message_id = meta.get('message_id')
        if message_id:
            error_message = (
                f"{UIStyles.header('Ошибка оплаты')}\n\n"
                f"{UIEmojis.ERROR} <b>Платеж не прошел!</b>\n\n"
                f"<b>Причина:</b> Платеж был отменен или возвращен\n"
                f"<b>Статус:</b> {status}\n\n"
                f"{UIStyles.description('Попробуйте оплатить заново или обратитесь в поддержку')}"
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Попробовать снова", callback_data=CallbackData.BUY_VPN)],
                [NavigationBuilder.create_main_menu_button()]
            ])
            
            await safe_edit_message_with_photo(
                bot_app.bot,
                chat_id=int(user_id),
                message_id=message_id,
                text=error_message,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type='payment_failed'
            )
            logger.info(f"Отправлено сообщение об ошибке оплаты пользователю {user_id}")
                    
    except Exception as e:
        logger.error(f"Ошибка обработки отмененного платежа {payment_id}: {e}")


async def process_failed_payment(bot_app, payment_id, user_id, meta, status):
    """Обрабатывает неудачный платеж"""
    try:
        await update_payment_status(payment_id, 'failed')
        await update_payment_activation(payment_id, 0)
        
        # Определяем тип платежа для правильного сообщения
        period = meta.get('type', 'month')
        is_extension = period.startswith('extend_')
        
        message_id = meta.get('message_id')
        if message_id:
            if is_extension:
                # Ошибка продления
                extension_email = meta.get('extension_key_email', 'Неизвестно')
                error_message = (
                    f"{UIStyles.header('Ошибка продления')}\n\n"
                    f"{UIEmojis.ERROR} <b>Платеж не прошел!</b>\n\n"
                    f"<b>Ключ:</b> {extension_email}\n"
                    f"<b>Причина:</b> Платеж был отклонен\n"
                    f"<b>Статус:</b> {status}\n\n"
                    f"{UIStyles.description('Попробуйте продлить заново или обратитесь в поддержку')}"
                )
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("Попробовать снова", callback_data=CallbackData.MY_KEYS)],
                    [NavigationBuilder.create_main_menu_button()]
                ])
                
                menu_type = 'extend_key'
            else:
                # Ошибка обычной покупки
                error_message = (
                    f"{UIStyles.header('Ошибка оплаты')}\n\n"
                    f"{UIEmojis.ERROR} <b>Платеж не прошел!</b>\n\n"
                    f"<b>Причина:</b> Платеж был отклонен\n"
                    f"<b>Статус:</b> {status}\n\n"
                    f"{UIStyles.description('Попробуйте оплатить заново или обратитесь в поддержку')}"
                )
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("Попробовать снова", callback_data=CallbackData.BUY_VPN)],
                    [NavigationBuilder.create_main_menu_button()]
                ])
                
                menu_type = 'payment_failed'
            
            await safe_edit_message_with_photo(
                bot_app.bot,
                chat_id=int(user_id),
                message_id=message_id,
                text=error_message,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type=menu_type
            )
            logger.info(f"Отправлено сообщение об ошибке пользователю {user_id}")
            
    except Exception as e:
        logger.error(f"Ошибка обработки неудачного платежа {payment_id}: {e}")

