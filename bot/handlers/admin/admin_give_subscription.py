"""
Админ-панель для выдачи подписки пользователю
"""
import logging
import datetime
import time
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters

from ...utils import UIEmojis, UIStyles, safe_edit_or_reply_universal, check_private_chat
from ...navigation import NavStates, CallbackData, MenuTypes, NavigationBuilder
from ...db import get_user_by_id
from ...db.subscribers_db import get_or_create_subscriber

logger = logging.getLogger(__name__)

# Константы для состояний ConversationHandler
GIVE_SUB_WAITING_USER_ID = 3001
GIVE_SUB_WAITING_PERIOD = 3002

def get_globals():
    """Получает глобальные переменные из bot.py"""
    try:
        from ... import bot as bot_module
        return {
            'ADMIN_IDS': getattr(bot_module, 'ADMIN_IDS', []),
            'subscription_manager': getattr(bot_module, 'subscription_manager', None),
            'new_client_manager': getattr(bot_module, 'new_client_manager', None),
            'nav_system': getattr(bot_module, 'nav_system', None),
        }
    except (ImportError, AttributeError):
        return {
            'ADMIN_IDS': [],
            'subscription_manager': None,
            'new_client_manager': None,
            'nav_system': None,
        }


async def admin_give_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса выдачи подписки - запрос user_id"""
    if not await check_private_chat(update):
        return ConversationHandler.END
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    # Если это callback_query, отвечаем на него
    if update.callback_query:
        from ...utils import safe_answer_callback_query
        await safe_answer_callback_query(update.callback_query)
    
    if update.effective_user.id not in ADMIN_IDS:
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply_universal(message_obj, 'Нет доступа.', menu_type=MenuTypes.ADMIN_MENU)
        return ConversationHandler.END
    
    # Очищаем старые данные
    context.user_data.pop('admin_give_sub_user_id', None)
    context.user_data.pop('admin_give_sub_menu_message_id', None)
    context.user_data.pop('admin_give_sub_menu_chat_id', None)
    
    # Если передан user_id как аргумент команды
    if update.message and context.args and len(context.args) > 0:
        user_id = context.args[0]
        await select_period(update, context, user_id)
        return ConversationHandler.END
    
    message = (
        f"{UIStyles.header('Выдача подписки пользователю')}\n\n"
        f"{UIStyles.description('Введите Telegram ID пользователя:')}\n\n"
        f"{UIStyles.description('Пример: 123456789')}"
    )
    
    keyboard = InlineKeyboardMarkup([
        [NavigationBuilder.create_back_button()]
    ])
    
    message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    result = await safe_edit_or_reply_universal(message_obj, message, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_MENU)
    
    # Сохраняем message_id меню для дальнейшего редактирования
    if message_obj:
        context.user_data['admin_give_sub_menu_message_id'] = message_obj.message_id
        context.user_data['admin_give_sub_menu_chat_id'] = message_obj.chat.id
    
    return GIVE_SUB_WAITING_USER_ID


async def admin_give_subscription_input_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ввод user_id"""
    if not await check_private_chat(update):
        return ConversationHandler.END
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END
    
    user_id = update.message.text.strip()
    
    # Удаляем сообщение пользователя с ID
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение пользователя: {e}")
    
    # Получаем message_id меню из context
    menu_message_id = context.user_data.get('admin_give_sub_menu_message_id')
    menu_chat_id = context.user_data.get('admin_give_sub_menu_chat_id')
    
    # Проверяем, существует ли пользователь
    from ...db import get_user_by_id
    user = await get_user_by_id(user_id)
    if not user:
        message = (
            f"{UIEmojis.ERROR} <b>Пользователь не найден</b>\n\n"
            f"Пользователь с ID <code>{user_id}</code> не найден в базе данных.\n\n"
            f"{UIStyles.description('Пользователь будет создан автоматически при выдаче подписки.')}"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Продолжить", callback_data=f"admin_give_sub_continue:{user_id}")],
            [NavigationBuilder.create_back_button()]
        ])
        
        if menu_chat_id and menu_message_id:
            from ...utils.message_helpers import safe_edit_message_with_photo
            bot = update.message.get_bot() if update.message else None
            if bot:
                try:
                    await safe_edit_message_with_photo(bot, menu_chat_id, menu_message_id, message, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_MENU)
                except Exception as e:
                    logger.error(f"Ошибка редактирования сообщения: {e}")
                    message_obj = update.message if update.message else None
                    if message_obj:
                        await safe_edit_or_reply_universal(message_obj, message, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_MENU)
        else:
            message_obj = update.message if update.message else None
            if message_obj:
                await safe_edit_or_reply_universal(message_obj, message, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_MENU)
        
        # Сохраняем user_id для продолжения
        context.user_data['admin_give_sub_user_id'] = user_id
        return ConversationHandler.END
    
    # Переходим к выбору периода
    await select_period(update, context, user_id, menu_chat_id=menu_chat_id, menu_message_id=menu_message_id)
    
    # Очищаем данные из context
    context.user_data.pop('admin_give_sub_menu_message_id', None)
    context.user_data.pop('admin_give_sub_menu_chat_id', None)
    
    return ConversationHandler.END


async def admin_give_subscription_continue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Продолжение выдачи подписки для несуществующего пользователя"""
    if not await check_private_chat(update):
        return
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    if update.callback_query:
        from ...utils import safe_answer_callback_query
        await safe_answer_callback_query(update.callback_query)
        
        # Извлекаем user_id из callback_data
        parts = update.callback_query.data.split(':', 1)
        if len(parts) > 1:
            user_id = parts[1]
            await select_period(update, context, user_id)
        else:
            user_id = context.user_data.get('admin_give_sub_user_id')
            if user_id:
                await select_period(update, context, user_id)


async def select_period(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str, menu_chat_id=None, menu_message_id=None):
    """Выбор периода подписки"""
    try:
        # Получаем информацию о пользователе (если существует)
        user = await get_user_by_id(user_id)
        user_info = ""
        if user:
            first_seen = datetime.datetime.fromtimestamp(user['first_seen']).strftime('%d.%m.%Y %H:%M')
            user_info = f"\n<b>Пользователь:</b> <code>{user_id}</code>\n<b>Первый запуск:</b> {first_seen}\n\n"
        else:
            user_info = f"\n<b>Пользователь:</b> <code>{user_id}</code> (будет создан)\n\n"
        
        message = (
            f"{UIStyles.header('Выдача подписки')}\n"
            f"{user_info}"
            f"{UIStyles.description('Выберите период подписки:')}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("1 месяц", callback_data=f"admin_give_sub_period:{user_id}:month")],
            [InlineKeyboardButton("3 месяца", callback_data=f"admin_give_sub_period:{user_id}:3month")],
            [NavigationBuilder.create_back_button()]
        ])
        
        # Используем menu_chat_id и menu_message_id для редактирования, если они есть
        if menu_chat_id and menu_message_id:
            from ...utils.message_helpers import safe_edit_message_with_photo
            bot = update.message.get_bot() if update.message else (update.callback_query.message.get_bot() if update.callback_query else None)
            if bot:
                try:
                    await safe_edit_message_with_photo(bot, menu_chat_id, menu_message_id, message, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_MENU)
                except Exception as e:
                    logger.error(f"Ошибка редактирования сообщения: {e}")
                    message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
                    if message_obj:
                        await safe_edit_or_reply_universal(message_obj, message, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_MENU)
        else:
            message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
            if message_obj:
                await safe_edit_or_reply_universal(message_obj, message, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_MENU)
        
        # Сохраняем user_id в context
        context.user_data['admin_give_sub_user_id'] = user_id
        
    except Exception as e:
        logger.exception("Ошибка в select_period")
        error_message = f"{UIEmojis.ERROR} Ошибка: {str(e)}"
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        if message_obj:
            await safe_edit_or_reply_universal(message_obj, error_message, menu_type=MenuTypes.ADMIN_MENU)


async def admin_give_subscription_period(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора периода и создание подписки"""
    if not await check_private_chat(update):
        return
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    if not update.callback_query:
        return
    
    from ...utils import safe_answer_callback_query
    await safe_answer_callback_query(update.callback_query)
    
    # Извлекаем user_id и period из callback_data
    parts = update.callback_query.data.split(':')
    if len(parts) < 3:
        await update.callback_query.message.reply_text(f"{UIEmojis.ERROR} Ошибка: неверный формат данных")
        return
    
    user_id = parts[1]
    period = parts[2]
    
    # Создаем подписку
    await create_subscription_for_user(update, context, user_id, period)


async def create_subscription_for_user(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str, period: str):
    """Создает подписку для пользователя"""
    try:
        globals_dict = get_globals()
        subscription_manager = globals_dict.get('subscription_manager')
        new_client_manager = globals_dict.get('new_client_manager')
        
        if not subscription_manager:
            error_msg = f"{UIEmojis.ERROR} <b>Ошибка</b>\n\nSubscriptionManager недоступен."
            message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
            await safe_edit_or_reply_universal(message_obj, error_msg, menu_type=MenuTypes.ADMIN_MENU)
            return
        
        if not new_client_manager:
            error_msg = f"{UIEmojis.ERROR} <b>Ошибка</b>\n\nNewClientManager недоступен."
            message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
            await safe_edit_or_reply_universal(message_obj, error_msg, menu_type=MenuTypes.ADMIN_MENU)
            return
        
        # Показываем сообщение о процессе
        process_msg = (
            f"{UIStyles.header('Создание подписки')}\n\n"
            f"{UIEmojis.INFO} Создание подписки для пользователя <code>{user_id}</code>...\n"
            f"Период: {period}"
        )
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply_universal(message_obj, process_msg, parse_mode="HTML", menu_type=MenuTypes.ADMIN_MENU)
        
        # Создаем подписку в БД
        device_limit = 1  # По умолчанию 1 устройство
        price = 0.0  # Бесплатно (выдано админом)
        
        sub_dict, token = await subscription_manager.create_subscription_for_user(
            user_id=user_id,
            period=period,
            device_limit=device_limit,
            price=price,
            name=None  # Автоматическое имя
        )
        
        subscription_id = sub_dict['id']
        expires_at = sub_dict['expires_at']
        
        logger.info(f"✅ Подписка создана в БД: subscription_id={subscription_id}, user_id={user_id}, period={period}")
        
        # Получаем все серверы из конфигурации
        all_configured_servers = []
        for server in new_client_manager.servers:
            server_name = server["name"]
            if server.get("x3") is not None:
                all_configured_servers.append(server_name)
        
        if all_configured_servers:
            # Генерируем уникальный email для клиента
            unique_email = f"{user_id}_{subscription_id}"
            
            logger.info(f"Создание клиентов на {len(all_configured_servers)} серверах для подписки {subscription_id}")
            
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
            successful_servers = []
            failed_servers = []
            for server_name in all_configured_servers:
                try:
                    client_exists, client_created = await subscription_manager.ensure_client_on_server(
                        subscription_id=subscription_id,
                        server_name=server_name,
                        client_email=unique_email,
                        user_id=user_id,
                        expires_at=expires_at,
                        token=token,
                        device_limit=device_limit
                    )
                    
                    if client_exists:
                        successful_servers.append(server_name)
                        if client_created:
                            logger.info(f"✅ Клиент создан на сервере {server_name}")
                        else:
                            logger.info(f"Клиент уже существует на сервере {server_name}")
                    else:
                        failed_servers.append(server_name)
                        logger.warning(f"Не удалось создать клиента на сервере {server_name} (будет создан при синхронизации)")
                except Exception as e:
                    logger.error(f"Ошибка создания клиента на сервере {server_name}: {e}")
                    failed_servers.append(server_name)
            
            logger.info(f"Подписка создана: успешно на {len(successful_servers)} серверах, ошибок: {len(failed_servers)}")
            
            # Формируем сообщение об успехе
            period_text = "3 месяца" if period == "3month" else "1 месяц"
            expiry_datetime = datetime.datetime.fromtimestamp(expires_at)
            expiry_str = expiry_datetime.strftime('%d.%m.%Y %H:%M')
            
            success_msg = (
                f"{UIStyles.success_message('✅ Подписка успешно выдана!')}\n\n"
                f"<b>Пользователь:</b> <code>{user_id}</code>\n"
                f"<b>Период:</b> {period_text}\n"
                f"<b>Истекает:</b> {expiry_str}\n"
                f"<b>Устройств:</b> {device_limit}\n"
                f"<b>ID подписки:</b> {subscription_id}\n\n"
            )
            
            if successful_servers:
                success_msg += f"{UIEmojis.SUCCESS} <b>Клиенты созданы на {len(successful_servers)} серверах</b>\n"
            
            if failed_servers:
                success_msg += f"\n{UIEmojis.WARNING} <b>Не удалось создать на {len(failed_servers)} серверах:</b>\n"
                success_msg += f"{', '.join(failed_servers)}\n"
                success_msg += f"{UIStyles.description('Клиенты будут созданы при следующей синхронизации.')}\n"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Подписки пользователя", callback_data=f"admin_user_subs:{user_id}")],
                [NavigationBuilder.create_back_button()]
            ])
        else:
            success_msg = (
                f"{UIStyles.success_message('✅ Подписка создана в БД!')}\n\n"
                f"<b>Пользователь:</b> <code>{user_id}</code>\n"
                f"<b>Период:</b> {period_text}\n"
                f"<b>ID подписки:</b> {subscription_id}\n\n"
                f"{UIEmojis.WARNING} <b>Нет серверов в конфигурации</b>\n"
                f"{UIStyles.description('Клиенты будут созданы при добавлении серверов и синхронизации.')}\n"
            )
            keyboard = InlineKeyboardMarkup([
                [NavigationBuilder.create_back_button()]
            ])
        
        await safe_edit_or_reply_universal(message_obj, success_msg, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_MENU)
        
        # Очищаем данные из context
        context.user_data.pop('admin_give_sub_user_id', None)
        context.user_data.pop('admin_give_sub_menu_message_id', None)
        context.user_data.pop('admin_give_sub_menu_chat_id', None)
        
    except Exception as e:
        logger.exception("Ошибка в create_subscription_for_user")
        error_msg = (
            f"{UIEmojis.ERROR} <b>Ошибка создания подписки</b>\n\n"
            f"{str(e)}"
        )
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        keyboard = InlineKeyboardMarkup([
            [NavigationBuilder.create_back_button()]
        ])
        await safe_edit_or_reply_universal(message_obj, error_msg, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_MENU)


async def admin_give_subscription_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена выдачи подписки"""
    if not await check_private_chat(update):
        return ConversationHandler.END
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END
    
    # Очищаем данные
    context.user_data.pop('admin_give_sub_user_id', None)
    context.user_data.pop('admin_give_sub_menu_message_id', None)
    context.user_data.pop('admin_give_sub_menu_chat_id', None)
    
    return ConversationHandler.END

