"""
Обработчик команды /admin_config
"""
import logging
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from ...utils import (
    UIEmojis, safe_edit_or_reply, check_private_chat
)
from ...navigation import NavigationBuilder
from ...db import get_all_config

logger = logging.getLogger(__name__)

# Импортируем глобальные переменные из bot.py
def get_globals():
    """Получает глобальные переменные из bot.py"""
    try:
        from ... import bot as bot_module
        return {
            'ADMIN_IDS': getattr(bot_module, 'ADMIN_IDS', []),
        }
    except (ImportError, AttributeError):
        return {'ADMIN_IDS': []}


async def admin_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает текущую конфигурацию"""
    if not await check_private_chat(update):
        return
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    if update.effective_user.id not in ADMIN_IDS:
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply(message_obj, 'Нет доступа.')
        return
    
    try:
        config = await get_all_config()
        message = "Конфигурация:\n\n"
        if config:
            for key, data in config.items():
                message += f"• {data['description']}: {data['value']}\n"
        else:
            message += "Конфигурация пуста."
        
        keyboard = InlineKeyboardMarkup([
            [NavigationBuilder.create_back_button()]
        ])
        
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply(message_obj, message, reply_markup=keyboard, parse_mode="Markdown")
        
    except Exception as e:
        logger.exception("Ошибка в admin_config")
        await safe_edit_or_reply(update.message, f'{UIEmojis.ERROR} Ошибка: {e}')

