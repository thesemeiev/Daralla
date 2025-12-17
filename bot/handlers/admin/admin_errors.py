"""
Обработчик команды /admin_errors
"""
import logging
import html
import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from ...utils import (
    UIEmojis, UIButtons, safe_edit_or_reply_universal, check_private_chat
)
from ...navigation import NavStates, CallbackData, nav_manager

logger = logging.getLogger(__name__)

# Импортируем глобальные переменные из bot.py
def get_globals():
    """Получает глобальные переменные из bot.py"""
    try:
        from ... import bot as bot_module
        return {
            'ADMIN_IDS': getattr(bot_module, 'ADMIN_IDS', []),
            'nav_system': getattr(bot_module, 'nav_system', None),
        }
    except (ImportError, AttributeError):
        return {
            'ADMIN_IDS': [],
            'nav_system': None,
        }


async def admin_errors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает последние логи ошибок"""
    if not await check_private_chat(update):
        return
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    nav_system = globals_dict['nav_system']
    
    # Добавляем состояние в стек только если функция вызывается напрямую (не через навигационную систему)
    # Если функция вызывается через навигационную систему, состояние уже добавлено в стек
    if update.callback_query and not context.user_data.get('_nav_called', False):
        from ...utils import safe_answer_callback_query
        await safe_answer_callback_query(update.callback_query)
        if nav_system:
            await nav_system.navigate_to_state(update, context, NavStates.ADMIN_ERRORS)
            return  # navigate_to_state уже вызвал эту функцию через MenuHandlers
    
    if update.effective_user.id not in ADMIN_IDS:
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply_universal(message_obj, 'Нет доступа.', menu_type='admin_errors')
        return
    
    try:
        # Читаем ротационный файл логов приложения
        from ...db import DATA_DIR
        logs_path = os.path.join(DATA_DIR, 'logs', 'bot.log')
        logs = ''
        if os.path.exists(logs_path):
            with open(logs_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                logs = ''.join(lines[-200:])  # последние ~200 строк
        else:
            logs = 'Файл логов не найден. Он будет создан автоматически при работе бота.'

        # Ограничиваем длину логов для Telegram (максимум 4000 символов)
        if len(logs) > 3500:  # Оставляем место для HTML тегов
            logs = logs[-3500:]

        # Экранируем HTML и выводим как код
        escaped = html.escape(logs)

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.REFRESH} Обновить", callback_data=CallbackData.ADMIN_ERRORS_REFRESH)],
            [UIButtons.back_button()]
        ])
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        
        # Используем фото для логов, ограничиваем длину для caption
        max_length = 800  # Telegram caption limit is 1024, but we use 800 to be safe
        if len(escaped) > max_length:
            escaped = escaped[:max_length] + "\n\n... (логи обрезаны)"
        
        logs_text = f"<b>Последние логи:</b>\n\n<pre><code>{escaped}</code></pre>"
        await safe_edit_or_reply_universal(message_obj, logs_text, reply_markup=keyboard, parse_mode='HTML', menu_type='admin_errors')
            
    except Exception as e:
        logger.exception("Ошибка в admin_errors")
        keyboard = InlineKeyboardMarkup([
            [UIButtons.back_button()]
        ])
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        
        # Используем фото для ошибки логов
        error_text = f'{UIEmojis.ERROR} Ошибка при чтении логов: {str(e)}'
        await safe_edit_or_reply_universal(message_obj, error_text, reply_markup=keyboard, menu_type='admin_errors')

