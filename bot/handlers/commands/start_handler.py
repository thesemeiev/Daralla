"""
Обработчик команды /start
"""
import logging
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from ...utils import (
    UIEmojis, UIStyles, UIButtons, UIMessages,
    safe_edit_or_reply_universal, check_private_chat
)
from ...db import register_simple_user
from ...navigation import NavStates, MenuTypes

logger = logging.getLogger(__name__)

# Импортируем глобальные переменные из bot.py
# Это временное решение до полного рефакторинга
def get_globals():
    """Получает глобальные переменные из bot.py"""
    try:
        from ... import bot as bot_module
        return {
            'ADMIN_IDS': getattr(bot_module, 'ADMIN_IDS', []),
            'new_client_manager': getattr(bot_module, 'new_client_manager', None),
        }
    except (ImportError, AttributeError):
        # Fallback если модуль еще не загружен
        return {'ADMIN_IDS': []}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    if not await check_private_chat(update):
        return
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    new_client_manager = globals_dict['new_client_manager']
    
    user_id = str(update.effective_user.id)
    
    # Используем единый стиль для приветственного сообщения
    welcome_text = UIMessages.welcome_message()
    
    # Создаем кнопки главного меню используя единый стиль
    is_admin = update.effective_user.id in ADMIN_IDS
    buttons = UIButtons.main_menu_buttons(is_admin=is_admin)
    keyboard = InlineKeyboardMarkup(buttons)
    
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if message is None:
        logger.error("main_menu: message is None")
        return
    
    # Дополнительное логирование для отладки
    logger.info(f"START_MESSAGE: message={message}, welcome_text_length={len(welcome_text) if welcome_text else 0}")

    # Теперь, когда все проверки выполнены, регистрируем пользователя
    try:
        await register_simple_user(user_id)
    except Exception as e:
        logger.error(f"Register user failed: {e}")
    
    # Добавляем главное меню в навигационный стек при старте
    globals_dict = get_globals()
    nav_system = globals_dict.get('nav_system')
    if nav_system:
        from ...navigation import nav_manager
        nav_manager.clear_stack(context)
        nav_manager.push_state(context, NavStates.MAIN_MENU)
    
    # Отправляем меню с фото
    await safe_edit_or_reply_universal(message, welcome_text, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.MAIN_MENU)


async def edit_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Редактирует существующее сообщение на главное меню"""
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    # Создаем кнопки главного меню используя единый стиль
    is_admin = update.effective_user.id in ADMIN_IDS
    buttons = UIButtons.main_menu_buttons(is_admin=is_admin)
    keyboard = InlineKeyboardMarkup(buttons)
    
    # Используем единый стиль для приветственного сообщения
    welcome_text = UIMessages.welcome_message()
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if message is None:
        logger.error("edit_main_menu: message is None")
        return
    
    logger.info(f"EDIT_MAIN_MENU: Редактируем сообщение {message.message_id}")
    try:
        # Отправляем меню с фото
        await safe_edit_or_reply_universal(message, welcome_text, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.MAIN_MENU)
        logger.info("EDIT_MAIN_MENU: Сообщение успешно отредактировано")
    except Exception as e:
        logger.error(f"EDIT_MAIN_MENU: Ошибка редактирования сообщения: {e}")
        # Если не удалось отредактировать, отправляем новое
        logger.info("EDIT_MAIN_MENU: Вызываем start() как fallback")
        await start(update, context)

