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
    safe_edit_message_with_photo, safe_send_message_with_photo
)
from ...navigation import NavigationBuilder, CallbackData, MenuTypes

logger = logging.getLogger(__name__)


def cleanup_extension_message_for_payment(payment_id):
    """Вспомогательная функция для очистки extension_messages"""
    try:
        from ... import bot as bot_module
        from ...utils.extension_messages_cleanup import cleanup_extension_messages
        if hasattr(bot_module, 'extension_messages'):
            cleanup_extension_messages(bot_module.extension_messages, payment_id)
    except Exception as e:
        logger.debug(f"Ошибка очистки extension_messages для payment_id={payment_id}: {e}")


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
        
        # Обрабатываем платеж в зависимости от статуса
        if status == 'succeeded':
            # Успешная оплата - создаем или продлеваем подписку
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
            # Обработка продления подписки
            await process_extension_payment(bot_app, payment_id, user_id, meta, message_id)
        else:
            # Обработка новой покупки подписки
            await process_new_purchase_payment(bot_app, payment_id, user_id, meta, message_id)
            
    except Exception as e:
        logger.error(f"Ошибка обработки успешного платежа {payment_id}: {e}")


async def process_extension_payment(bot_app, payment_id, user_id, meta, message_id):
    """Обрабатывает продление подписки"""
    try:
        period = meta.get('type', 'month')
        # Убираем префиксы: extend_sub_month -> month, extend_sub_3month -> 3month
        actual_period = period
        if period.startswith('extend_sub_'):
            actual_period = period.replace('extend_sub_', '', 1)
        elif period.startswith('extend_'):
            actual_period = period.replace('extend_', '', 1)
        days = 90 if actual_period == '3month' else 30
        
        # Проверяем, это продление подписки
        is_subscription_extension = period.startswith('extend_sub_')
        extension_subscription_id = meta.get('extension_subscription_id')
        
        if is_subscription_extension:
            # Продление подписки
            logger.info(f"Обработка продления подписки: subscription_id={extension_subscription_id}, period={period}, actual_period={actual_period}, days={days}")
            
            if not extension_subscription_id:
                logger.error(f"Не найден subscription_id для продления в meta: {meta}")
                await update_payment_status(payment_id, 'failed')
                cleanup_extension_message_for_payment(payment_id)
                return
            
            # Получаем глобальные переменные
            globals_dict = get_globals()
            subscription_manager = globals_dict.get('subscription_manager')
            new_client_manager = globals_dict.get('new_client_manager')
            
            if not subscription_manager or not new_client_manager:
                logger.error("subscription_manager или new_client_manager не доступен")
                await update_payment_status(payment_id, 'failed')
                cleanup_extension_message_for_payment(payment_id)
                return
            
            # Проверяем, что подписка принадлежит пользователю
            from ...db.subscribers_db import get_subscription_by_id, get_subscription_servers
            sub = await get_subscription_by_id(extension_subscription_id, user_id)
            
            if not sub:
                logger.error(f"Попытка продлить чужую подписку: user_id={user_id}, subscription_id={extension_subscription_id}")
                await update_payment_status(payment_id, 'failed')
                cleanup_extension_message_for_payment(payment_id)
                return
            
            # Получаем информацию о подписке
            servers = await get_subscription_servers(extension_subscription_id)
            
            if not servers:
                logger.error(f"Не найдены серверы для подписки {extension_subscription_id}")
                await update_payment_status(payment_id, 'failed')
                cleanup_extension_message_for_payment(payment_id)
                return
            
            # Шаг 1: Вычисляем новое время истечения и обновляем БД
            # Это делаем ПЕРВЫМ, чтобы БД была источником истины
            import time
            current_time = int(time.time())
            if sub:
                # Вычисляем новое время истечения
                current_expires_at = sub['expires_at']
                # Если подписка уже истекла, начинаем с текущего времени, иначе продлеваем от текущего expires_at
                base_time = max(current_expires_at, current_time)
                new_expires_at = base_time + days * 24 * 60 * 60
                
                # Обновляем expires_at в БД ПЕРЕД синхронизацией серверов
                from ...db.subscribers_db import update_subscription_expiry
                await update_subscription_expiry(extension_subscription_id, new_expires_at)
                logger.info(f"Подписка {extension_subscription_id} продлена до {new_expires_at} в БД")
            else:
                # Если подписка не найдена, используем текущее время + дни
                new_expires_at = current_time + days * 24 * 60 * 60
                logger.warning(f"Подписка {extension_subscription_id} не найдена в БД, используем расчетное время: {new_expires_at}")
            
            # Шаг 2: Синхронизируем время на всех серверах через ensure_client_on_server
            # Эта функция сама проверит время на сервере и синхронизирует его с БД
            successful_extensions = []
            failed_extensions = []
            
            # Получаем device_limit из подписки для передачи в ensure_client_on_server
            device_limit = sub.get('device_limit', 1) if sub else 1
            
            for server_info in servers:
                server_name = server_info['server_name']
                client_email = server_info['client_email']
                
                try:
                    # Используем ensure_client_on_server с НОВЫМ expires_at
                    # Он сам проверит время на сервере и синхронизирует его с БД и limitIp
                    client_exists, client_created = await subscription_manager.ensure_client_on_server(
                        subscription_id=extension_subscription_id,
                        server_name=server_name,
                        client_email=client_email,
                        user_id=user_id,
                        expires_at=new_expires_at,  # Используем НОВОЕ время из БД
                        token=sub['subscription_token'] if sub else '',
                        device_limit=device_limit  # Передаем device_limit для синхронизации limitIp
                    )
                    
                    if client_exists:
                        successful_extensions.append(server_name)
                        if client_created:
                            logger.info(f"Клиент создан на сервере {server_name} для подписки {extension_subscription_id}")
                        else:
                            logger.info(f"Время клиента синхронизировано на сервере {server_name} для подписки {extension_subscription_id}")
                    else:
                        logger.warning(f"Не удалось синхронизировать клиента на сервере {server_name}")
                        failed_extensions.append(server_name)
                except Exception as e:
                    # Ошибка при синхронизации - логируем и добавляем в failed
                    logger.error(f"Ошибка синхронизации клиента на сервере {server_name}: {e}")
                    failed_extensions.append(server_name)
            
            # Проверяем, что синхронизация прошла успешно хотя бы на одном сервере
            if not successful_extensions:
                logger.error(f"Не удалось синхронизировать клиентов ни на одном сервере для подписки {extension_subscription_id}")
                await update_payment_status(payment_id, 'failed')
                cleanup_extension_message_for_payment(payment_id)
                # Уведомляем пользователя
                if message_id:
                    error_message = (
                        f"{UIStyles.header('Ошибка продления подписки')}\n\n"
                        f"{UIEmojis.ERROR} <b>Не удалось продлить подписку!</b>\n\n"
                        f"<b>Причина:</b> Не удалось синхронизировать клиентов на серверах\n\n"
                        f"{UIStyles.description('Попробуйте позже или обратитесь в поддержку')}"
                    )
                    # Создаем кнопку для открытия мини-приложения
                    from ...utils import UIButtons
                    webapp_button = UIButtons.create_webapp_button(
                        action='subscriptions'
                    )
                    
                    buttons = []
                    if webapp_button:
                        buttons.append([webapp_button])
                    
                    # Оставляем старые кнопки для совместимости
                    buttons.extend([
                        [InlineKeyboardButton("Попробовать снова", callback_data=CallbackData.SUBSCRIPTIONS_MENU)],
                        [NavigationBuilder.create_main_menu_button()]
                    ])
                    
                    keyboard = InlineKeyboardMarkup(buttons)
                    await safe_edit_message_with_photo(
                        bot_app.bot,
                        chat_id=int(user_id),
                        message_id=message_id,
                        text=error_message,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        menu_type=MenuTypes.PAYMENT_SUCCESS
                    )
                return
            
            # Проверяем, что синхронизация прошла на всех серверах
            if failed_extensions:
                logger.warning(
                    f"Продление подписки {extension_subscription_id} прошло не на всех серверах: "
                    f"успешно на {len(successful_extensions)} серверах, "
                    f"ошибки на {len(failed_extensions)} серверах: {failed_extensions}. "
                    f"Серверы будут синхронизированы при следующей автоматической синхронизации."
                )
            
            await update_payment_status(payment_id, 'succeeded')
            await update_payment_activation(payment_id, 1)
            
            # Очищаем запись из extension_messages после успешной обработки
            try:
                from ... import bot as bot_module
                from ...utils.extension_messages_cleanup import cleanup_extension_messages
                if hasattr(bot_module, 'extension_messages'):
                    cleanup_extension_messages(bot_module.extension_messages, payment_id)
            except Exception as e:
                logger.warning(f"Ошибка очистки extension_messages для payment_id={payment_id}: {e}")
            
            # Записываем факт продления подписки для анализа эффективности уведомлений
            try:
                globals_dict = get_globals()
                notification_manager = globals_dict.get('notification_manager')
                if notification_manager:
                    # Передаем user_id и subscription_id для записи эффективности
                    await notification_manager.record_subscription_extension(user_id, extension_subscription_id)
            except Exception as e:
                logger.warning(f"Ошибка записи продления подписки для уведомлений: {e}")
            
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
                    f"<b>Серверов продлено:</b> {len(successful_extensions)} из {len(servers)}\n\n"
                )
                
                if failed_extensions:
                    extension_message += (
                        f"{UIEmojis.WARNING} <b>Внимание!</b> Не удалось продлить на серверах: {', '.join(failed_extensions)}\n\n"
                        f"{UIStyles.description('Клиент должен быть на всех серверах подписки. Обратитесь в поддержку для решения проблемы.')}\n\n"
                    )
                
                extension_message += f"{UIStyles.description('Подписка активна и готова к использованию.')}"
                
                if message_id:
                    # Создаем кнопку для открытия мини-приложения
                    from ...utils import UIButtons
                    webapp_button = UIButtons.create_webapp_button(
                        action='subscription',
                        params=extension_subscription_id
                    )
                    
                    buttons = []
                    if webapp_button:
                        buttons.append([webapp_button])
                    
                    # Оставляем старые кнопки для совместимости
                    buttons.extend([
                        [InlineKeyboardButton("Мои подписки", callback_data=CallbackData.SUBSCRIPTIONS_MENU)],
                        [NavigationBuilder.create_main_menu_button()]
                    ])
                    
                    keyboard = InlineKeyboardMarkup(buttons)
                    
                    await safe_edit_message_with_photo(
                        bot_app.bot,
                        chat_id=int(user_id),
                        message_id=message_id,
                        text=extension_message,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        menu_type=MenuTypes.PAYMENT_SUCCESS
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
                        menu_type=MenuTypes.PAYMENT_SUCCESS
                    )
                    logger.info(f"Отправлено новое сообщение о продлении подписки {extension_subscription_id} пользователю {user_id}")
                    
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления о продлении подписки: {e}")
            
            return
        else:
            # Это не продление подписки - ошибка
            logger.error(f"Неизвестный тип продления: period={period}, meta={meta}")
            await update_payment_status(payment_id, 'failed')
            return
                    
    except Exception as e:
        logger.error(f"Ошибка обработки продления подписки {payment_id}: {e}")


async def process_new_purchase_payment(bot_app, payment_id, user_id, meta, message_id):
    """Обрабатывает новую покупку - создаёт подписку и клиентов на всех доступных серверах"""
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
            
            # Используем правильный формат email: {user_id}_{subscription_id}
            # Вместо UUID из метаданных платежа используем реальный subscription_id
            unique_email = f"{user_id}_{sub_dict['id']}"
            logger.info(f"Используется правильный формат email: {unique_email} (вместо UUID из метаданных)")
        except Exception as sub_e:
            logger.error(f"Ошибка при создании подписки для user_id={user_id}: {sub_e}")
            await update_payment_status(payment_id, 'failed')
            return
        
        # Шаг 2: Получаем ВСЕ серверы из конфигурации (не только здоровые)
        # Гибридный подход: привязываем все серверы к подписке сразу,
        # но создаем клиентов только на доступных. Нездоровые серверы
        # будут синхронизированы автоматически при следующей синхронизации.
        all_configured_servers = []
        for server in new_client_manager.servers:
            server_name = server["name"]
            if server.get("x3") is not None:
                all_configured_servers.append(server_name)
        
        if not all_configured_servers:
            logger.error("Нет серверов в конфигурации")
            await update_payment_status(payment_id, 'failed')
            # Уведомляем пользователя
            try:
                error_message = (
                    f"{UIStyles.header('Ошибка создания подписки')}\n\n"
                    f"{UIEmojis.ERROR} <b>Не удалось создать подписку!</b>\n\n"
                    f"<b>Причина:</b> Нет серверов в конфигурации\n\n"
                    f"{UIStyles.description('Обратитесь в поддержку')}"
                )
                # Создаем кнопку для открытия мини-приложения
                from ...utils import UIButtons
                webapp_button = UIButtons.create_webapp_button(
                    action='subscriptions'
                )
                
                buttons = []
                if webapp_button:
                    buttons.append([webapp_button])
                
                # Оставляем старые кнопки для совместимости
                buttons.append([NavigationBuilder.create_main_menu_button()])
                
                keyboard = InlineKeyboardMarkup(buttons)
                await safe_edit_message_with_photo(
                    bot_app.bot,
                    chat_id=int(user_id),
                    message_id=message_id,
                    text=error_message,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    menu_type=MenuTypes.PAYMENT
                )
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения об ошибке: {e}")
            return
        
        # Шаг 3: Создаём клиента на каждом сервере из конфигурации
        # Используем единую функцию ensure_client_on_server для гарантии наличия клиента
        # Используем токен подписки как subId для связи клиента с подпиской в X-UI
        # Гибридный подход: привязываем все серверы к подписке, создаем клиентов на доступных
        successful_servers = []
        failed_servers = []
        
        # Получаем expires_at из подписки
        expires_at = sub_dict.get('expires_at') if sub_dict else None
        if not expires_at:
            import time
            expires_at = int(time.time()) + days * 24 * 60 * 60
        
        # Сначала привязываем ВСЕ серверы к подписке в БД (даже если недоступны)
        # Это гарантирует, что все серверы будут в подписке сразу
        for server_name in all_configured_servers:
            try:
                # Привязываем сервер к подписке в БД (даже если он недоступен)
                # Клиент будет создан автоматически при синхронизации, если сервер недоступен сейчас
                await subscription_manager.attach_server_to_subscription(
                    subscription_id=sub_dict["id"],
                    server_name=server_name,
                    client_email=unique_email,
                    client_id=None,
                )
                logger.info(f"Сервер {server_name} привязан к подписке {sub_dict['id']}")
            except Exception as attach_e:
                # Если сервер уже привязан, это нормально (идемпотентность)
                if "UNIQUE constraint" in str(attach_e) or "already exists" in str(attach_e).lower():
                    logger.info(f"Сервер {server_name} уже привязан к подписке {sub_dict['id']}")
                else:
                    logger.error(f"Ошибка привязки сервера {server_name} к подписке: {attach_e}")
        
        # Теперь пытаемся создать клиентов на всех серверах
        # Если сервер недоступен - клиент будет создан при синхронизации
        for server_name in all_configured_servers:
            try:
                # Используем единую функцию ensure_client_on_server
                # Она гарантирует наличие клиента и синхронизирует время истечения
                client_exists, client_created = await subscription_manager.ensure_client_on_server(
                    subscription_id=sub_dict["id"],
                    server_name=server_name,
                    client_email=unique_email,
                    user_id=user_id,
                    expires_at=expires_at,
                    token=token
                )
                
                if client_exists:
                    successful_servers.append((server_name, unique_email))
                    # Сервер уже привязан к подписке выше, просто логируем результат
                    if client_created:
                        logger.info(f"Клиент создан на сервере {server_name} для подписки {sub_dict['id']}")
                    else:
                        logger.info(f"Клиент уже существует на сервере {server_name}")
                else:
                    # Сервер недоступен или ошибка создания
                    # Это не критично - клиент будет создан при синхронизации
                    # Сервер уже привязан к подписке выше
                    logger.warning(f"Не удалось создать клиента на сервере {server_name} (будет создан при синхронизации)")
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
                    await update_subscription_status(sub_dict['id'], 'deleted')
                    logger.info(f"Подписка {sub_dict['id']} удалена из-за ошибки создания клиентов (компенсирующая транзакция)")
                except Exception as rollback_e:
                    logger.error(f"Ошибка отката подписки {sub_dict['id']}: {rollback_e}")
            
            await update_payment_status(payment_id, 'failed')
            # Уведомляем пользователя
            try:
                error_message = (
                    f"{UIStyles.header('Ошибка создания подписки')}\n\n"
                    f"{UIEmojis.ERROR} <b>Не удалось создать подписку!</b>\n\n"
                    f"<b>Причина:</b> Не удалось создать клиентов на серверах\n\n"
                    f"{UIStyles.description('Попробуйте позже или обратитесь в поддержку')}"
                )
                # Создаем кнопку для открытия мини-приложения
                from ...utils import UIButtons
                webapp_button = UIButtons.create_webapp_button(
                    action='subscriptions'
                )
                
                buttons = []
                if webapp_button:
                    buttons.append([webapp_button])
                
                # Оставляем старые кнопки для совместимости
                buttons.append([NavigationBuilder.create_main_menu_button()])
                
                keyboard = InlineKeyboardMarkup(buttons)
                await safe_edit_message_with_photo(
                    bot_app.bot,
                    chat_id=int(user_id),
                    message_id=message_id,
                    text=error_message,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    menu_type=MenuTypes.PAYMENT
                )
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения об ошибке: {e}")
            return
        
        # Шаг 4: Обновляем статус платежа
        # Подписка создана успешно, если хотя бы на одном сервере клиент создан
        # Нездоровые серверы уже привязаны к подписке, клиенты будут созданы при синхронизации
        await update_payment_status(payment_id, 'succeeded')
        await update_payment_activation(payment_id, 1)
        
        # Логируем результаты
        if failed_servers:
            logger.info(
                f"Подписка {sub_dict['id']} создана: "
                f"клиенты созданы на {len(successful_servers)} серверах, "
                f"на {len(failed_servers)} серверах будут созданы при синхронизации: {failed_servers}"
            )
        else:
            logger.info(f"Подписка {sub_dict['id']} создана: клиенты созданы на всех {len(successful_servers)} серверах")
        
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

            # Получаем главное название VPN для параметра в URL
            try:
                from ... import bot as bot_module
                vpn_brand_name = getattr(bot_module, 'VPN_BRAND_NAME', 'Daralla VPN')
            except (ImportError, AttributeError):
                vpn_brand_name = 'Daralla VPN'
            
            # Формируем subscription URL
            # Для Happ клиента лучше использовать поддомен (как делают другие разработчики: auth.zkodes.ru)
            # Happ использует домен из URL как название группы подписки
            import urllib.parse
            
            # Проверяем, есть ли специальный URL для подписок (поддомен)
            subscription_base_url = os.getenv("SUBSCRIPTION_URL", "").rstrip("/")
            
            # Если SUBSCRIPTION_URL не установлен, извлекаем базовый URL из WEBHOOK_URL
            # (убираем путь /webhook/yookassa, оставляем только домен)
            if subscription_base_url:
                base_url = subscription_base_url
            elif webhook_url:
                # Извлекаем базовый URL (домен) из WEBHOOK_URL
                parsed = urllib.parse.urlparse(webhook_url)
                base_url = f"{parsed.scheme}://{parsed.netloc}"
            else:
                base_url = None
            
            if base_url:
                # Для Happ клиента используем поддомен в URL (например: daralla-vpn.ghosttunnel.space)
                # Happ автоматически использует поддомен (или первую часть) как название группы
                # Параметр name убираем, так как он может вызывать проблемы с эмодзи и 502 ошибки
                # Поддомен в URL - это основной способ для Happ
                subscription_url = f"{base_url}/sub/{token}"
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
                subscription_message += f"\n\n{UIEmojis.WARNING} <i>Не удалось создать клиентов на серверах: {', '.join(failed_servers)}</i>"
            
            # Создаем кнопку для открытия мини-приложения
            from ...utils import UIButtons
            webapp_button = UIButtons.create_webapp_button(
                action='subscription',
                params=sub_dict['id'] if sub_dict else None
            )
            
            buttons = []
            if webapp_button:
                buttons.append([webapp_button])
            
            # Оставляем старые кнопки для совместимости
            buttons.extend([
                [InlineKeyboardButton("Мои подписки", callback_data=CallbackData.SUBSCRIPTIONS_MENU)],
                [NavigationBuilder.create_main_menu_button()]
            ])
            
            keyboard = InlineKeyboardMarkup(buttons)
            
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
            # Для платежей из мини-приложения message_id может быть None - не отправляем сообщение в бот
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
                        menu_type=MenuTypes.PAYMENT_SUCCESS
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
                        menu_type=MenuTypes.PAYMENT_SUCCESS
                    )
                    logger.info(f"Отправлено новое сообщение с подпиской для user_id={user_id}")
            else:
                # Если нет message_id (платеж из мини-приложения), не отправляем сообщение в бот
                # Пользователь уже видит уведомление в мини-приложении через polling
                logger.info(f"Платеж из мини-приложения для user_id={user_id} - сообщение в бот не отправляется (нет message_id)")
                
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
                menu_type=MenuTypes.PAYMENT_FAILED
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
                # Ошибка продления подписки
                extension_subscription_id = meta.get('extension_subscription_id', 'Неизвестно')
                error_message = (
                    f"{UIStyles.header('Ошибка продления подписки')}\n\n"
                    f"{UIEmojis.ERROR} <b>Платеж не прошел!</b>\n\n"
                    f"<b>Подписка ID:</b> {extension_subscription_id}\n"
                    f"<b>Причина:</b> Платеж был отклонен\n"
                    f"<b>Статус:</b> {status}\n\n"
                    f"{UIStyles.description('Попробуйте продлить заново или обратитесь в поддержку')}"
                )
                
                # Создаем кнопку для открытия мини-приложения
                from ...utils import UIButtons
                webapp_button = UIButtons.create_webapp_button(
                    action='subscriptions'
                )
                
                buttons = []
                if webapp_button:
                    buttons.append([webapp_button])
                
                # Оставляем старые кнопки для совместимости
                buttons.extend([
                    [InlineKeyboardButton("Попробовать снова", callback_data=CallbackData.SUBSCRIPTIONS_MENU)],
                    [NavigationBuilder.create_main_menu_button()]
                ])
                
                keyboard = InlineKeyboardMarkup(buttons)
                
                menu_type = MenuTypes.SUBSCRIPTIONS_MENU
            else:
                # Ошибка обычной покупки
                error_message = (
                    f"{UIStyles.header('Ошибка оплаты')}\n\n"
                    f"{UIEmojis.ERROR} <b>Платеж не прошел!</b>\n\n"
                    f"<b>Причина:</b> Платеж был отклонен\n"
                    f"<b>Статус:</b> {status}\n\n"
                    f"{UIStyles.description('Попробуйте оплатить заново или обратитесь в поддержку')}"
                )
                
                # Создаем кнопку для открытия мини-приложения
                from ...utils import UIButtons
                webapp_button = UIButtons.create_webapp_button(
                    action='subscriptions'
                )
                
                buttons = []
                if webapp_button:
                    buttons.append([webapp_button])
                
                # Оставляем старые кнопки для совместимости
                buttons.extend([
                    [InlineKeyboardButton("Попробовать снова", callback_data=CallbackData.BUY_VPN)],
                    [NavigationBuilder.create_main_menu_button()]
                ])
                
                keyboard = InlineKeyboardMarkup(buttons)
                
                menu_type = MenuTypes.PAYMENT_FAILED
            
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

