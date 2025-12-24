"""
Обработчик промокодов
"""
import logging
import time
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from ...utils import UIEmojis, safe_edit_or_reply_universal, safe_answer_callback_query, safe_edit_message_with_photo
from ...navigation import NavigationBuilder, MenuTypes, CallbackData
from ...db.subscribers_db import (
    use_promo_code, get_or_create_subscriber, 
    create_subscription, get_subscription_servers, update_subscription_expiry, get_subscription_by_id
)
from ...db import get_config

logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
PROMO_WAITING_CODE = 1

def get_globals():
    """Получает глобальные переменные из bot.py"""
    try:
        from ... import bot as bot_module
        return {
            'subscription_manager': getattr(bot_module, 'subscription_manager', None),
            'new_client_manager': getattr(bot_module, 'new_client_manager', None),
            'nav_system': getattr(bot_module, 'nav_system', None),
        }
    except (ImportError, AttributeError):
        return {
            'subscription_manager': None,
            'new_client_manager': None,
            'nav_system': None,
        }


async def promo_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало ввода промокода"""
    query = update.callback_query
    
    if query:
        await safe_answer_callback_query(query)
        message = query.message
    else:
        message = update.message
    
    # Определяем тип промокода из callback_data
    callback_data = query.data if query else None
    promo_type = None
    subscription_id = None
    
    if callback_data:
        if callback_data.startswith('promo_purchase'):
            promo_type = 'purchase'
        elif callback_data.startswith('promo_extend:'):
            promo_type = 'extension'
            parts = callback_data.split(':')
            if len(parts) > 1:
                try:
                    subscription_id = int(parts[1])
                except ValueError:
                    pass
    
    # Сохраняем в контекст
    context.user_data['promo_type'] = promo_type or 'purchase'
    context.user_data['promo_subscription_id'] = subscription_id
    context.user_data['promo_message_id'] = message.message_id
    context.user_data['promo_chat_id'] = message.chat_id
    
    text = (
        f"<b>Введите промокод</b>\n\n"
        f"Отправьте промокод для {'покупки' if promo_type == 'purchase' else 'продления'} подписки.\n\n"
        f"<i>Один промокод можно использовать для покупки и продления.</i>"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{UIEmojis.PREV} Отмена", callback_data='promo_cancel')]
    ])
    
    await safe_edit_or_reply_universal(
        message,
        text,
        reply_markup=keyboard,
        parse_mode="HTML",
        menu_type=MenuTypes.BUY_MENU if promo_type == 'purchase' else MenuTypes.SUBSCRIPTIONS_MENU
    )
    
    return PROMO_WAITING_CODE


async def promo_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка введенного промокода"""
    user = update.effective_user
    user_id = str(user.id)
    promo_code = update.message.text.strip().upper()
    
    # Удаляем сообщение пользователя
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение пользователя: {e}")
    
    promo_type = context.user_data.get('promo_type', 'purchase')
    subscription_id = context.user_data.get('promo_subscription_id')
    message_id = context.user_data.get('promo_message_id')
    chat_id = context.user_data.get('promo_chat_id')
    
    # Проверяем активный промокод из конфигурации
    active_promo_code = await get_config('active_promo_code', None)
    active_promo_period = await get_config('active_promo_period', 'month')
    
    # Проверяем, совпадает ли введенный промокод с активным
    if not active_promo_code or promo_code.upper() != active_promo_code.upper():
        error_msg = "Промокод не найден или не активен"
    else:
        error_msg = None
        # Создаем promo_data из конфигурации (тип не нужен, промокод универсальный)
        promo_data = {
            'code': active_promo_code,
            'period': active_promo_period
        }
    
    if error_msg:
        text = (
            f"{UIEmojis.ERROR} <b>Промокод недействителен</b>\n\n"
            f"{error_msg}\n\n"
            f"Попробуйте ввести другой промокод."
        )
        
        keyboard = InlineKeyboardMarkup([
            [NavigationBuilder.create_back_button()]
        ])
        
        try:
            await safe_edit_message_with_photo(
                context.bot,
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type=MenuTypes.BUY_MENU if promo_type == 'purchase' else MenuTypes.SUBSCRIPTIONS_MENU
            )
        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")
            # Fallback: пытаемся отредактировать как текст
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            except Exception as e2:
                logger.error(f"Ошибка редактирования как текст: {e2}")
                await safe_edit_or_reply_universal(
                    update.message,
                    text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    menu_type=MenuTypes.BUY_MENU if promo_type == 'purchase' else MenuTypes.SUBSCRIPTIONS_MENU
                )
        
        # Очищаем контекст
        context.user_data.pop('promo_type', None)
        context.user_data.pop('promo_subscription_id', None)
        context.user_data.pop('promo_message_id', None)
        context.user_data.pop('promo_chat_id', None)
        
        return -1  # Завершаем ConversationHandler
    
    # Применяем промокод
    try:
        if promo_type == 'purchase':
            # Создаем новую подписку
            await apply_promo_purchase(update, context, user_id, promo_code, promo_data)
        else:
            # Продлеваем существующую подписку
            await apply_promo_extension(update, context, user_id, promo_code, promo_data, subscription_id)
        
        # Отмечаем промокод как использованный (увеличиваем счетчик, но не проверяем повторное использование)
        subscription_id_for_use = context.user_data.get('created_subscription_id') if promo_type == 'purchase' else subscription_id
        await use_promo_code(promo_code, user_id, subscription_id_for_use)
        
    except Exception as e:
        logger.exception(f"Ошибка применения промокода: {e}")
        text = (
            f"{UIEmojis.ERROR} <b>Ошибка применения промокода</b>\n\n"
            f"Произошла ошибка при применении промокода. Попробуйте позже."
        )
        
        keyboard = InlineKeyboardMarkup([
            [NavigationBuilder.create_back_button()]
        ])
        
        try:
            await safe_edit_message_with_photo(
                context.bot,
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type=MenuTypes.BUY_MENU if promo_type == 'purchase' else MenuTypes.SUBSCRIPTIONS_MENU
            )
        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")
            # Fallback: пытаемся отредактировать как текст
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            except Exception as e2:
                logger.error(f"Ошибка редактирования как текст: {e2}")
                await safe_edit_or_reply_universal(
                    update.message,
                    text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    menu_type=MenuTypes.BUY_MENU if promo_type == 'purchase' else MenuTypes.SUBSCRIPTIONS_MENU
                )
    
    # Очищаем контекст
    context.user_data.pop('promo_type', None)
    context.user_data.pop('promo_subscription_id', None)
    context.user_data.pop('promo_message_id', None)
    context.user_data.pop('promo_chat_id', None)
    context.user_data.pop('created_subscription_id', None)
    
    return -1  # Завершаем ConversationHandler


async def promo_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена ввода промокода"""
    query = update.callback_query
    if query:
        await safe_answer_callback_query(query)
        message = query.message
    else:
        message = update.message
    
    promo_type = context.user_data.get('promo_type', 'purchase')
    
    # Очищаем контекст
    context.user_data.pop('promo_type', None)
    context.user_data.pop('promo_subscription_id', None)
    context.user_data.pop('promo_message_id', None)
    context.user_data.pop('promo_chat_id', None)
    
    # Возвращаемся в соответствующее меню
    from ...navigation.menu_handlers import MenuHandlers
    menu_handlers = MenuHandlers()
    
    if promo_type == 'purchase':
        await menu_handlers.buy_menu(update, context)
    else:
        from ...handlers.commands.mykey_handler import mykey
        await mykey(update, context)
    
    return -1


async def apply_promo_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str, promo_code: str, promo_data: dict):
    """Применяет промокод для покупки новой подписки"""
    globals_dict = get_globals()
    subscription_manager = globals_dict['subscription_manager']
    new_client_manager = globals_dict['new_client_manager']
    
    if not subscription_manager or not new_client_manager:
        raise Exception("SubscriptionManager или NewClientManager не доступен")
    
    period = promo_data['period']
    message_id = context.user_data.get('promo_message_id')
    chat_id = context.user_data.get('promo_chat_id')
    
    # Создаем подписку
    subscriber_id = await get_or_create_subscriber(user_id)
    
    # Вычисляем expires_at
    import datetime
    now = int(time.time())
    if period == 'month':
        expires_at = now + (30 * 24 * 60 * 60)
    else:  # 3month
        expires_at = now + (90 * 24 * 60 * 60)
    
    subscription_id, token = await create_subscription(
        subscriber_id=subscriber_id,
        period=period,
        device_limit=1,
        price=0.0,  # Бесплатно по промокоду
        expires_at=expires_at,
        name="Промокод"
    )
    
    context.user_data['created_subscription_id'] = subscription_id
    
    # Синхронизируем серверы и создаем клиентов на всех доступных серверах
    await subscription_manager.sync_servers_with_config(auto_create_clients=True)
    servers = await get_subscription_servers(subscription_id)
    
    for server_info in servers:
        server_name = server_info['server_name']
        client_email = server_info['client_email']
        
        await subscription_manager.ensure_client_on_server(
            subscription_id=subscription_id,
            server_name=server_name,
            client_email=client_email,
            user_id=user_id,
            expires_at=expires_at,
            token=token,
            device_limit=1
        )
    
    # Показываем "прикольное" сообщение о взломе
    period_text = "1 месяц" if period == 'month' else "3 месяца"
    
    hack_message = (
        f"<b>ВЗЛОМ УСПЕШЕН!</b>\n\n"
        f"<i>Система безопасности была обойдена...</i>\n\n"
        f"<b>Вам выдана подписка на {period_text}</b>\n\n"
        f"<b>Промокод:</b> <code>{promo_code}</code>\n\n"
        f"Подписка активирована и включает все доступные серверы!\n\n"
        f"<i>Это сообщение будет удалено через 10 секунд...</i>\n\n"
        f"<b>Наслаждайтесь!</b>"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Мои подписки", callback_data=CallbackData.SUBSCRIPTIONS_MENU)],
        [NavigationBuilder.create_back_button()]
    ])
    
    # Обновляем навигационный стек - сохраняем предыдущее состояние
    from ...navigation import nav_manager, NavStates
    # Получаем promo_type из контекста
    promo_type_from_context = context.user_data.get('promo_type', 'purchase')
    # Если пользователь пришел из покупки, добавляем BUY_MENU, иначе SUBSCRIPTIONS_MENU
    if promo_type_from_context == 'purchase':
        nav_manager.push_state(context, NavStates.BUY_MENU)
    else:
        nav_manager.push_state(context, NavStates.SUBSCRIPTIONS_MENU)
    
    try:
        await safe_edit_message_with_photo(
            context.bot,
            chat_id=chat_id,
            message_id=message_id,
            text=hack_message,
            reply_markup=keyboard,
            parse_mode="HTML",
            menu_type=MenuTypes.PROMO_HACK
        )
    except Exception as e:
        logger.error(f"Ошибка редактирования сообщения: {e}")
        # Fallback: пытаемся отредактировать как текст
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=hack_message,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception as e2:
            logger.error(f"Ошибка редактирования как текст: {e2}")
            await safe_edit_or_reply_universal(
                update.message,
                hack_message,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type=MenuTypes.PROMO_HACK
            )


async def apply_promo_extension(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str, promo_code: str, promo_data: dict, subscription_id: int):
    """Применяет промокод для продления подписки"""
    
    globals_dict = get_globals()
    subscription_manager = globals_dict['subscription_manager']
    
    if not subscription_manager:
        raise Exception("SubscriptionManager не доступен")
    
    # Проверяем, что подписка принадлежит пользователю
    sub = await get_subscription_by_id(subscription_id, user_id)
    if not sub:
        raise Exception("Подписка не найдена или не принадлежит вам")
    
    period = promo_data['period']
    message_id = context.user_data.get('promo_message_id')
    chat_id = context.user_data.get('promo_chat_id')
    
    # Вычисляем новую дату истечения
    import datetime
    now = int(time.time())
    current_expires = sub['expires_at']
    
    # Если подписка уже истекла, начинаем с текущего времени
    if current_expires < now:
        new_expires_at = now
    else:
        new_expires_at = current_expires
    
    # Добавляем период
    if period == 'month':
        new_expires_at += (30 * 24 * 60 * 60)
    else:  # 3month
        new_expires_at += (90 * 24 * 60 * 60)
    
    # Обновляем подписку
    await update_subscription_expiry(subscription_id, new_expires_at)
    
    # Обновляем клиентов на серверах
    servers = await get_subscription_servers(subscription_id)
    token = sub['subscription_token']
    
    for server_info in servers:
        server_name = server_info['server_name']
        client_email = server_info['client_email']
        
        await subscription_manager.ensure_client_on_server(
            subscription_id=subscription_id,
            server_name=server_name,
            client_email=client_email,
            user_id=user_id,
            expires_at=new_expires_at,
            token=token,
            device_limit=sub.get('device_limit', 1)
        )
    
    # Показываем "прикольное" сообщение о взломе
    period_text = "1 месяц" if period == 'month' else "3 месяца"
    
    hack_message = (
        f"<b>ВЗЛОМ УСПЕШЕН!</b>\n\n"
        f"<i>Система безопасности была обойдена...</i>\n\n"
        f"<b>Ваша подписка продлена на {period_text}</b>\n\n"
        f"<b>Промокод:</b> <code>{promo_code}</code>\n\n"
        f"Подписка обновлена на всех серверах!\n\n"
        f"<i>Это сообщение будет удалено через 10 секунд...</i>\n\n"
        f"<b>Наслаждайтесь!</b>"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Мои подписки", callback_data=CallbackData.SUBSCRIPTIONS_MENU)],
        [NavigationBuilder.create_back_button()]
    ])
    
    # Обновляем навигационный стек - сохраняем предыдущее состояние
    from ...navigation import nav_manager, NavStates
    # Получаем promo_type из контекста
    promo_type_from_context = context.user_data.get('promo_type', 'purchase')
    # Если пользователь пришел из покупки, добавляем BUY_MENU, иначе SUBSCRIPTIONS_MENU
    if promo_type_from_context == 'purchase':
        nav_manager.push_state(context, NavStates.BUY_MENU)
    else:
        nav_manager.push_state(context, NavStates.SUBSCRIPTIONS_MENU)
    
    try:
        await safe_edit_message_with_photo(
            context.bot,
            chat_id=chat_id,
            message_id=message_id,
            text=hack_message,
            reply_markup=keyboard,
            parse_mode="HTML",
            menu_type=MenuTypes.PROMO_HACK
        )
    except Exception as e:
        logger.error(f"Ошибка редактирования сообщения: {e}")
        # Fallback: пытаемся отредактировать как текст
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=hack_message,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        except Exception as e2:
            logger.error(f"Ошибка редактирования как текст: {e2}")
            await safe_edit_or_reply_universal(
                update.message,
                hack_message,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type=MenuTypes.PROMO_HACK
            )

