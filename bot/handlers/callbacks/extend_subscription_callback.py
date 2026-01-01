"""
Обработчик callback'ов для продления подписок
"""
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from ...utils import (
    UIEmojis, UIStyles, safe_edit_or_reply_universal, safe_answer_callback_query
)
from ...navigation import CallbackData, NavigationBuilder, MenuTypes

logger = logging.getLogger(__name__)

# Импортируем глобальные переменные из bot.py
def get_globals():
    """Получает глобальные переменные из bot.py"""
    try:
        import sys
        import importlib
        # Пытаемся получить модуль bot.bot
        if 'bot.bot' in sys.modules:
            bot_module = sys.modules['bot.bot']
        else:
            bot_module = importlib.import_module('bot.bot')
        
        # Пытаемся получить handle_payment напрямую из модуля или через импорт
        handle_payment_func = getattr(bot_module, 'handle_payment', None)
        if handle_payment_func is None:
            # Если не найдено в модуле, импортируем напрямую
            from ...handlers.payments import handle_payment as hp
            handle_payment_func = hp
        
        return {
            'subscription_manager': getattr(bot_module, 'subscription_manager', None),
            'handle_payment': handle_payment_func,
        }
    except (ImportError, AttributeError) as e:
        logger.warning(f"Не удалось получить глобальные переменные: {e}")
        # Fallback: импортируем напрямую
        try:
            from ...handlers.payments import handle_payment as hp
            return {
                'subscription_manager': None,
                'handle_payment': hp,
            }
        except ImportError:
            return {
                'subscription_manager': None,
                'handle_payment': None,
            }


async def extend_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback'а для продления подписки"""
    query = update.callback_query
    
    # Отвечаем на callback query СРАЗУ, до любых долгих операций
    await safe_answer_callback_query(query)
    
    user = query.from_user
    user_id = str(user.id)
    
    globals_dict = get_globals()
    subscription_manager = globals_dict['subscription_manager']
    handle_payment = globals_dict['handle_payment']
    
    if not subscription_manager:
        await safe_edit_or_reply_universal(
            query.message,
            f"{UIEmojis.ERROR} Ошибка: система подписок не настроена",
            reply_markup=InlineKeyboardMarkup([[NavigationBuilder.create_back_button()]]),
            menu_type=MenuTypes.SUBSCRIPTIONS_MENU
        )
        return
    
    if not handle_payment:
        await safe_edit_or_reply_universal(
            query.message,
            f"{UIEmojis.ERROR} Ошибка: система платежей не настроена",
            reply_markup=InlineKeyboardMarkup([[NavigationBuilder.create_back_button()]]),
            menu_type=MenuTypes.SUBSCRIPTIONS_MENU
        )
        return
    
    # Извлекаем subscription_id из callback_data: extend_sub:subscription_id
    parts = query.data.split(":", 1)
    if len(parts) < 2:
        await safe_edit_or_reply_universal(
            query.message,
            f"{UIEmojis.ERROR} Ошибка: неверный формат данных",
            reply_markup=InlineKeyboardMarkup([[NavigationBuilder.create_back_button()]]),
            menu_type=MenuTypes.SUBSCRIPTIONS_MENU
        )
        return
    
    try:
        subscription_id = int(parts[1])
    except ValueError:
        await safe_edit_or_reply_universal(
            query.message,
            f"{UIEmojis.ERROR} Ошибка: неверный ID подписки",
            reply_markup=InlineKeyboardMarkup([[NavigationBuilder.create_back_button()]]),
            menu_type=MenuTypes.SUBSCRIPTIONS_MENU
        )
        return
    
    # Проверяем, что подписка принадлежит пользователю
    from ...db.subscribers_db import get_subscription_by_id
    sub = await get_subscription_by_id(subscription_id, user_id)
    
    if not sub:
        await safe_edit_or_reply_universal(
            query.message,
            f"{UIEmojis.ERROR} Ошибка: подписка не найдена или не принадлежит вам",
            reply_markup=InlineKeyboardMarkup([[NavigationBuilder.create_back_button()]]),
            menu_type=MenuTypes.SUBSCRIPTIONS_MENU
        )
        return
    
    # Проверяем, что подписка не удалена/отменена (разрешаем продление активных и истекших подписок)
    import time
    if sub['status'] == 'deleted':
        await safe_edit_or_reply_universal(
            query.message,
            f"{UIEmojis.ERROR} Ошибка: подписка была отменена или удалена",
            reply_markup=InlineKeyboardMarkup([[NavigationBuilder.create_back_button()]]),
            menu_type=MenuTypes.SUBSCRIPTIONS_MENU
        )
        return
    
    logger.info(f"Запрос на продление подписки: user_id={user_id}, subscription_id={subscription_id}")
    
    # Показываем меню выбора периода продления
    from ...utils import UIButtons
    webapp_button = UIButtons.create_webapp_button(
        action='subscriptions',
        text="Назад к списку"
    )
    
    keyboard_buttons = [
        [InlineKeyboardButton("1 месяц - 150₽", callback_data=f"{CallbackData.EXT_SUB_PER}month:{subscription_id}")],
        [InlineKeyboardButton("3 месяца - 350₽", callback_data=f"{CallbackData.EXT_SUB_PER}3month:{subscription_id}")],
        [InlineKeyboardButton("Промокод", callback_data=f"{CallbackData.PROMO_EXTEND}:{subscription_id}")]
    ]
    
    if webapp_button:
        keyboard_buttons.append([webapp_button])
    else:
        keyboard_buttons.append([InlineKeyboardButton(f"{UIEmojis.PREV} Назад", callback_data=CallbackData.SUBSCRIPTIONS_MENU)])
    
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    
    # Получаем количество серверов подписки
    from ...db.subscribers_db import get_subscription_servers
    servers = await get_subscription_servers(subscription_id)
    server_count = len(servers)
    
    # Форматируем дату истечения
    import datetime
    expiry_datetime = datetime.datetime.fromtimestamp(sub['expires_at'])
    expiry_str = expiry_datetime.strftime('%d.%m.%Y %H:%M')
    
    message_text = (
        f"{UIStyles.header('Продление подписки')}\n\n"
        f"<b>Подписка:</b> {sub.get('name', 'Подписка')}\n"
        f"<b>Истекает:</b> {expiry_str}\n"
        f"<b>Серверов:</b> {server_count}\n\n"
        f"{UIStyles.description('Выберите период продления:')}"
    )
    
    await safe_edit_or_reply_universal(
        query.message,
        message_text,
        reply_markup=keyboard,
        parse_mode="HTML",
        menu_type=MenuTypes.SUBSCRIPTIONS_MENU
    )


async def extend_subscription_period_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора периода для продления подписки"""
    query = update.callback_query
    
    # Отвечаем на callback query СРАЗУ, до любых долгих операций
    await safe_answer_callback_query(query)
    
    user = query.from_user
    user_id = str(user.id)
    
    globals_dict = get_globals()
    handle_payment = globals_dict['handle_payment']
    
    if not handle_payment:
        await safe_edit_or_reply_universal(
            query.message,
            f"{UIEmojis.ERROR} Ошибка: система платежей не настроена",
            reply_markup=InlineKeyboardMarkup([[NavigationBuilder.create_back_button()]]),
            menu_type=MenuTypes.SUBSCRIPTIONS_MENU
        )
        return
    
    # Извлекаем период и subscription_id из callback_data: {CallbackData.EXT_SUB_PER}month:subscription_id
    parts = query.data.split(":", 2)
    if len(parts) < 3:
        await safe_edit_or_reply_universal(
            query.message,
            f"{UIEmojis.ERROR} Ошибка: неверный формат данных",
            reply_markup=InlineKeyboardMarkup([[NavigationBuilder.create_back_button()]]),
            menu_type=MenuTypes.SUBSCRIPTIONS_MENU
        )
        return
    
    period = parts[1]  # month или 3month
    try:
        subscription_id = int(parts[2])
    except ValueError:
        await safe_edit_or_reply_universal(
            query.message,
            f"{UIEmojis.ERROR} Ошибка: неверный ID подписки",
            reply_markup=InlineKeyboardMarkup([[NavigationBuilder.create_back_button()]]),
            menu_type=MenuTypes.SUBSCRIPTIONS_MENU
        )
        return
    
    # Проверяем, что подписка принадлежит пользователю
    from ...db.subscribers_db import get_subscription_by_id
    sub = await get_subscription_by_id(subscription_id, user_id)
    
    if not sub:
        await safe_edit_or_reply_universal(
            query.message,
            f"{UIEmojis.ERROR} Ошибка: подписка не найдена или не принадлежит вам",
            reply_markup=InlineKeyboardMarkup([[NavigationBuilder.create_back_button()]]),
            menu_type=MenuTypes.SUBSCRIPTIONS_MENU
        )
        return
    
    # Проверяем, что подписка не удалена/отменена (разрешаем продление активных и истекших подписок)
    import time
    if sub['status'] == 'deleted':
        await safe_edit_or_reply_universal(
            query.message,
            f"{UIEmojis.ERROR} Ошибка: подписка была отменена или удалена",
            reply_markup=InlineKeyboardMarkup([[NavigationBuilder.create_back_button()]]),
            menu_type=MenuTypes.SUBSCRIPTIONS_MENU
        )
        return
    
    logger.info(f"Выбран период продления подписки: user_id={user_id}, period={period}, subscription_id={subscription_id}")
    
    # Определяем цену (такую же как при покупке)
    price = "150.00" if period == "month" else "350.00"  # в рублях
    
    # Создаем платеж для продления подписки
    try:
        # Сохраняем информацию о продлении в контексте
        context.user_data['extension_subscription_id'] = subscription_id
        context.user_data['extension_period'] = period
        
        # Вызываем функцию создания платежа
        await handle_payment(update, context, price, f"extend_sub_{period}")
        
    except Exception as e:
        logger.error(f"Ошибка создания платежа для продления подписки: {e}")
        from ...utils import UIButtons
        webapp_button = UIButtons.create_webapp_button(
            action='subscriptions',
            text="Назад к списку"
        )
        
        if webapp_button:
            keyboard = InlineKeyboardMarkup([[webapp_button]])
        else:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{UIEmojis.PREV} Назад", callback_data=CallbackData.SUBSCRIPTIONS_MENU)]
            ])
        await safe_edit_or_reply_universal(
            query.message,
            "Ошибка при создании платежа. Попробуйте позже.",
            reply_markup=keyboard,
            menu_type=MenuTypes.SUBSCRIPTIONS_MENU
        )

