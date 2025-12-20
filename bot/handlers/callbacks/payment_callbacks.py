"""
Обработчики callback-ов для платежей и выбора периода
"""

import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from ...navigation import NavStates, CallbackData, MenuHandlers, MenuTypes
from ...utils import UIEmojis, safe_edit_or_reply, safe_answer_callback_query
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger(__name__)

# Импортируем глобальные переменные из bot.py
def get_globals():
    """Получает глобальные переменные из bot.py"""
    try:
        import sys
        import importlib
        # Пытаемся получить модуль bot.bot (как это сделано в других местах)
        # Когда модуль запускается через "python -m bot.bot", он доступен как '__main__'
        # но мы также сохраняем ссылку на него под именем 'bot.bot'
        bot_module = None
        nav_system = None
        
        # Сначала пробуем получить из bot.bot
        if 'bot.bot' in sys.modules:
            bot_module = sys.modules['bot.bot']
            nav_system = getattr(bot_module, 'nav_system', None)
            logger.debug("get_globals: Проверен sys.modules['bot.bot']")
        
        # Если не нашли, пробуем __main__
        if nav_system is None and '__main__' in sys.modules:
            main_module = sys.modules['__main__']
            nav_system = getattr(main_module, 'nav_system', None)
            if nav_system is not None:
                bot_module = main_module
                logger.debug("get_globals: Найден nav_system в __main__")
        
        # Если все еще не нашли, пробуем импортировать
        if nav_system is None:
            try:
                bot_module = importlib.import_module('bot.bot')
                nav_system = getattr(bot_module, 'nav_system', None)
                logger.debug("get_globals: Загружен модуль bot.bot через importlib")
            except ImportError:
                logger.warning("get_globals: Не удалось импортировать bot.bot")
        
        if nav_system is None:
            logger.warning("get_globals: nav_system is None после всех попыток")
        else:
            logger.debug("get_globals: nav_system успешно получен")
        
        # Если bot_module не найден, используем значения по умолчанию
        if bot_module is None:
            return {
                'nav_system': nav_system,
                'handle_payment': None,
                'SERVERS_BY_LOCATION': {},
                'new_client_manager': None,
            }
        
        return {
            'nav_system': nav_system,
            'handle_payment': getattr(bot_module, 'handle_payment', None),
            'SERVERS_BY_LOCATION': getattr(bot_module, 'SERVERS_BY_LOCATION', {}),
            'new_client_manager': getattr(bot_module, 'new_client_manager', None),
        }
    except (ImportError, AttributeError) as e:
        logger.warning(f"Не удалось получить глобальные переменные: {e}")
        return {
            'nav_system': None,
            'handle_payment': None,
            'SERVERS_BY_LOCATION': {},
            'new_client_manager': None,
        }

async def select_period_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора периода подписки (1 подписка = 1 устройство, без выбора сервера)"""
    query = update.callback_query
    
    # Отвечаем на callback query СРАЗУ, до любых долгих операций
    await safe_answer_callback_query(query)
    
    logger.info(f"SELECT_PERIOD_CALLBACK: {query.data}")
    
    # Определяем период и цену
    if query.data == "select_period_month":
        period = "month"
        price = "150.00"
    elif query.data == "select_period_3month":
        period = "3month"
        price = "350.00"
    else:
        logger.error(f"SELECT_PERIOD_CALLBACK: неизвестный период {query.data}")
        await safe_edit_or_reply(query.message, f"{UIEmojis.ERROR} Неверный выбор тарифа")
        return
    
    # Сохраняем в контекст
    context.user_data["pending_period"] = period
    context.user_data["pending_price"] = price
    
    # Запускаем процесс оплаты сразу, без выбора сервера
    globals_dict = get_globals()
    handle_payment = globals_dict["handle_payment"]
    await handle_payment(update, context, price, period)


async def start_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback-кнопок для главного меню"""
    query = update.callback_query
    
    # Отвечаем на callback query СРАЗУ, до любых долгих операций
    await safe_answer_callback_query(query)
    
    logger.info(f"Обработка callback: {query.data}")
    
    globals_dict = get_globals()
    nav_system = globals_dict['nav_system']
    
    # ВАЖНО: "buy_menu" больше не обрабатывается здесь, так как в UI используется "buy_vpn"
    # который обрабатывается через NavigationIntegration
    # Оставляем только специфичные callback'и, которые не обрабатываются навигационной системой
    if query.data == "buy_menu":
        # Fallback для старого callback_data (если где-то еще используется)
        if not nav_system:
            logger.error("start_callback_handler: nav_system is None при обработке buy_menu (navigation required)")
            await safe_edit_or_reply(
                query.message,
                f"{UIEmojis.ERROR} Внутренняя ошибка навигации. Попробуйте позже."
            )
            return

        await nav_system.navigate_to_state(update, context, NavStates.BUY_MENU)
    elif query.data.startswith("select_period_"):
        await select_period_callback(update, context)
    elif query.data in ["mykey", "my_subs", "subs_menu"]:
        # Используем навигационную систему для перехода к "Мои подписки"
        if nav_system:
            await nav_system.navigate_to_state(update, context, NavStates.SUBSCRIPTIONS_MENU)
        else:
            from ..commands import mykey
            await mykey(update, context)
    # ВАЖНО: "instruction" и "mykeys_menu" обрабатываются через NavigationIntegration, поэтому убраны отсюда
    elif query.data == "admin_notifications_refresh":
        # Обновляем админ уведомления напрямую
        from ..admin import admin_notifications
        await admin_notifications(update, context)
    elif query.data == "admin_errors_refresh":
        # Обновляем админ логи напрямую
        from ..admin import admin_errors
        await admin_errors(update, context)
    # Обработка "back" убрана отсюда - она обрабатывается через NavigationIntegration
    # Это позволяет правильно работать навигационному стеку
