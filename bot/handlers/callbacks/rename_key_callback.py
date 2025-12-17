"""
Обработчик callback'ов для переименования ключей
"""
import logging
import json
import hashlib
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from ...utils import (
    UIEmojis, UIStyles, safe_edit_or_reply, safe_edit_or_reply_universal, safe_answer_callback_query
)
from ...utils.ui import UIButtons
from ...navigation import CallbackData

logger = logging.getLogger(__name__)

# Импортируем глобальные переменные из bot.py
def get_globals():
    """Получает глобальные переменные из bot.py"""
    try:
        from ... import bot as bot_module
        return {
            'server_manager': getattr(bot_module, 'server_manager', None),
        }
    except (ImportError, AttributeError):
        return {'server_manager': None}


async def rename_key_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик переименования ключа"""
    query = update.callback_query
    
    # Отвечаем на callback query СРАЗУ, до любых долгих операций
    await safe_answer_callback_query(query)
    
    globals_dict = get_globals()
    server_manager = globals_dict['server_manager']
    
    if not server_manager:
        await safe_edit_or_reply(query.message, f"{UIEmojis.ERROR} Ошибка: серверы не настроены")
        return
    
    user_id = str(query.from_user.id)
    short_id = query.data.split(':')[1]
    
    try:
        # Ищем ключ по short_id
        key_email = None
        unavailable_servers = []
        for server in server_manager.servers:
            try:
                xui = server["x3"]
                if xui is None:
                    logger.warning(f"Сервер {server['name']} недоступен, пропускаем")
                    unavailable_servers.append(server['name'])
                    continue
                inbounds = xui.list()['obj']
                for inbound in inbounds:
                    settings = json.loads(inbound['settings'])
                    clients = settings.get("clients", [])
                    for client in clients:
                        if client['email'].startswith(f"{user_id}_") or client['email'].startswith(f"trial_{user_id}_"):
                            # Проверяем short_id
                            possible_short_ids = [
                                hashlib.md5(f"rename:{client['email']}".encode()).hexdigest()[:8]
                            ]
                            if short_id in possible_short_ids:
                                key_email = client['email']
                                break
                    if key_email:
                        break
                if key_email:
                    break
            except Exception as e:
                logger.error(f"Ошибка при поиске ключа на сервере {server['name']}: {e}")
                unavailable_servers.append(server['name'])
                continue
        
        # Если все серверы недоступны, уведомляем пользователя
        if unavailable_servers and len(unavailable_servers) == len(server_manager.servers):
            error_message = (
                f"{UIStyles.header('Ошибка переименования')}\n\n"
                f"{UIEmojis.ERROR} <b>Все серверы временно недоступны!</b>\n\n"
                f"{UIStyles.description('Не удалось найти ключ для переименования. Попробуйте позже.')}"
            )
            keyboard = InlineKeyboardMarkup([
                [UIButtons.back_button()]
            ])
            await safe_edit_or_reply_universal(query.message, error_message, reply_markup=keyboard, parse_mode="HTML", menu_type='rename_key')
            return
        
        if not key_email:
            # Если есть недоступные серверы, сообщаем об этом
            if unavailable_servers:
                error_message = (
                    f"{UIStyles.header('Ошибка переименования')}\n\n"
                    f"{UIEmojis.ERROR} <b>Ключ не найден</b>\n\n"
                    f"{UIEmojis.WARNING} Некоторые серверы недоступны: {', '.join(unavailable_servers)}\n\n"
                    f"{UIStyles.description('Ключ не найден на доступных серверах.')}"
                )
            else:
                error_message = f"{UIEmojis.ERROR} Ключ не найден!"
            await safe_edit_or_reply(query.message, error_message, parse_mode="HTML" if unavailable_servers else None)
            return
        
        # Сохраняем email ключа и message_id в контексте для последующего использования
        context.user_data['rename_key_email'] = key_email
        context.user_data['rename_message_id'] = query.message.message_id
        context.user_data['rename_chat_id'] = query.message.chat_id
        
        # Запрашиваем новое имя ключа
        message = (
            f"{UIStyles.header('Переименование ключа')}\n\n"
            f"<b>Текущий ключ:</b> <code>{key_email}</code>\n\n"
            f"{UIStyles.description('Введите новое имя для ключа (максимум 50 символов):')}\n\n"
            f"{UIStyles.warning_message('Имя будет отображаться в списке ваших ключей')}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [UIButtons.back_button()]
        ])
        
        await safe_edit_or_reply_universal(query.message, message, reply_markup=keyboard, parse_mode="HTML", menu_type='rename_key')
        
        # Устанавливаем состояние ожидания ввода имени
        context.user_data['waiting_for_key_name'] = True
        
    except Exception as e:
        logger.error(f"Ошибка в rename_key_callback: {e}")
        await safe_edit_or_reply(query.message, f"{UIEmojis.ERROR} Ошибка при переименовании ключа!")

