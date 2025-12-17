"""
Обработчик команды /instruction
"""
import logging
from telegram import Update, InlineKeyboardButton
from telegram.ext import ContextTypes

from ...utils import (
    UIMessages, safe_edit_or_reply_universal, check_private_chat
)
from ...navigation import NavStates, CallbackData, NavigationBuilder

logger = logging.getLogger(__name__)

# Импортируем глобальные переменные из bot.py
def get_globals():
    """Получает глобальные переменные из bot.py"""
    try:
        from ... import bot as bot_module
        return {
            'nav_system': getattr(bot_module, 'nav_system', None),
        }
    except (ImportError, AttributeError):
        return {'nav_system': None}


async def instruction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /instruction"""
    if not await check_private_chat(update):
        return
    
    globals_dict = get_globals()
    nav_system = globals_dict['nav_system']
    
    # Добавляем состояние в стек только если функция вызывается напрямую (не через навигационную систему)
    # Если функция вызывается через навигационную систему, состояние уже добавлено в стек
    if update.callback_query and not context.user_data.get('_nav_called', False):
        from ...utils import safe_answer_callback_query
        await safe_answer_callback_query(update.callback_query)
        if nav_system:
            await nav_system.navigate_to_state(update, context, NavStates.INSTRUCTION_MENU)
            return  # navigate_to_state уже вызвал эту функцию через MenuHandlers
    
    keyboard = NavigationBuilder.create_keyboard_with_back([
        [InlineKeyboardButton("Android", callback_data=CallbackData.INSTR_ANDROID), InlineKeyboardButton("iOS", callback_data=CallbackData.INSTR_IOS)],
        [InlineKeyboardButton("Windows", callback_data=CallbackData.INSTR_WINDOWS), InlineKeyboardButton("macOS", callback_data=CallbackData.INSTR_MACOS)],
        [InlineKeyboardButton("Linux", callback_data=CallbackData.INSTR_LINUX), InlineKeyboardButton("Android TV", callback_data=CallbackData.INSTR_TV)],
        [InlineKeyboardButton("FAQ", callback_data=CallbackData.INSTR_FAQ)],
    ])
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if message is None:
        logger.error("instruction_menu: message is None")
        return
    
    # Используем единый стиль для сообщения
    instruction_text = UIMessages.instruction_menu_message()
    await safe_edit_or_reply_universal(message, instruction_text, reply_markup=keyboard, parse_mode="HTML", menu_type='instruction_menu')

