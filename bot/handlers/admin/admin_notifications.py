"""
Обработчик команды /admin_notifications
"""
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from ...utils import (
    UIEmojis, UIButtons, safe_edit_or_reply_universal, safe_edit_or_reply, check_private_chat
)
from ...navigation import NavStates, CallbackData, MenuTypes
from ...services import NotificationManager

logger = logging.getLogger(__name__)

# Импортируем глобальные переменные из bot.py
def get_globals():
    """Получает глобальные переменные из bot.py"""
    try:
        from ... import bot as bot_module
        return {
            'ADMIN_IDS': getattr(bot_module, 'ADMIN_IDS', []),
            'server_manager': getattr(bot_module, 'server_manager', None),
            'notification_manager': getattr(bot_module, 'notification_manager', None),
            'nav_system': getattr(bot_module, 'nav_system', None),
        }
    except (ImportError, AttributeError):
        return {
            'ADMIN_IDS': [],
            'server_manager': None,
            'notification_manager': None,
            'nav_system': None,
        }


async def admin_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Дашборд уведомлений для админа"""
    if not await check_private_chat(update):
        return
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    server_manager = globals_dict['server_manager']
    notification_manager = globals_dict['notification_manager']
    nav_system = globals_dict['nav_system']
    
    # Добавляем состояние в стек только если функция вызывается напрямую (не через навигационную систему)
    # Если функция вызывается через навигационную систему, состояние уже добавлено в стек
    if update.callback_query and not context.user_data.get('_nav_called', False):
        from ...utils import safe_answer_callback_query
        await safe_answer_callback_query(update.callback_query)
        if nav_system:
            await nav_system.navigate_to_state(update, context, NavStates.ADMIN_NOTIFICATIONS)
            return  # navigate_to_state уже вызвал эту функцию через MenuHandlers
    
    if update.effective_user.id not in ADMIN_IDS:
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply(message_obj, 'Нет доступа.')
        return
    
    try:
        # Получаем или инициализируем менеджер уведомлений
        if notification_manager is None:
            # Попробуем инициализировать менеджер уведомлений
            try:
                if not server_manager:
                    await safe_edit_or_reply(update.callback_query.message if update.callback_query else update.message, 
                                           f"{UIEmojis.ERROR} Серверы не настроены")
                    return
                
                # Создаем новый экземпляр менеджера
                new_notification_manager = NotificationManager(context.bot, server_manager, ADMIN_IDS)
                await new_notification_manager.initialize()
                await new_notification_manager.start()
                
                # Сохраняем в глобальную переменную (если возможно)
                try:
                    from ... import bot as bot_module
                    bot_module.notification_manager = new_notification_manager
                except:
                    pass
                
                logger.info("Менеджер уведомлений инициализирован в admin_notifications")
                notification_manager = new_notification_manager
            except Exception as e:
                logger.error(f"Ошибка инициализации менеджера уведомлений: {e}")
                await safe_edit_or_reply(update.callback_query.message if update.callback_query else update.message, 
                                       f"{UIEmojis.ERROR} Менеджер уведомлений не инициализирован")
                return
        
        # Получаем дашборд
        dashboard_text = await notification_manager.get_notification_dashboard()
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.REFRESH} Обновить", callback_data=CallbackData.ADMIN_NOTIFICATIONS_REFRESH)],
            [UIButtons.back_button()]
        ])
        
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        
        # Используем фото для уведомлений
        await safe_edit_or_reply_universal(message_obj, dashboard_text, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_NOTIFICATIONS)
        
    except Exception as e:
        logger.error(f"Ошибка в admin_notifications: {e}")
        keyboard = InlineKeyboardMarkup([
            [UIButtons.back_button()]
        ])
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        
        # Используем фото для ошибки уведомлений
        error_text = f"{UIEmojis.ERROR} Ошибка загрузки дашборда: {e}"
        await safe_edit_or_reply_universal(message_obj, error_text, reply_markup=keyboard, menu_type=MenuTypes.ADMIN_NOTIFICATIONS)

