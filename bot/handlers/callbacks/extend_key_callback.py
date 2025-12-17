"""
Обработчик callback'ов для продления ключей
"""
import logging
import json
import datetime
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
            'extension_keys_cache': getattr(bot_module, 'extension_keys_cache', {}),
        }
    except (ImportError, AttributeError):
        return {
            'server_manager': None,
            'extension_keys_cache': {},
        }


async def extend_key_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback'а для продления ключа"""
    query = update.callback_query
    
    # Отвечаем на callback query СРАЗУ, до любых долгих операций
    # Это предотвращает ошибку "Query is too old"
    await safe_answer_callback_query(query)
    
    user = query.from_user
    user_id = str(user.id)
    
    globals_dict = get_globals()
    server_manager = globals_dict['server_manager']
    extension_keys_cache = globals_dict['extension_keys_cache']
    
    if not server_manager:
        await safe_edit_or_reply(query.message, f"{UIEmojis.ERROR} Ошибка: серверы не настроены")
        return
    
    # Извлекаем short_id из callback_data
    parts = query.data.split(":", 1)
    if len(parts) < 2:
        await safe_edit_or_reply(query.message, f"{UIEmojis.ERROR} Ошибка: неверный формат данных")
        return
    
    short_id = parts[1]
    
    # Получаем email ключа из кэша
    cached_value = extension_keys_cache.get(short_id)
    key_email = cached_value['email'] if isinstance(cached_value, dict) else cached_value
    if not key_email:
        # Пытаемся найти ключ по short_id, созданному из уведомления
        # Проверяем все возможные форматы short_id
        
        # Ищем ключ пользователя на серверах
        try:
            all_clients = []
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
                                all_clients.append(client)
                except Exception as e:
                    logger.error(f"Ошибка при поиске ключей на сервере {server['name']}: {e}")
                    unavailable_servers.append(server['name'])
                    continue
            
            # Если все серверы недоступны, уведомляем пользователя
            if unavailable_servers and len(unavailable_servers) == len(server_manager.servers):
                error_message = (
                    f"{UIStyles.header('Ошибка продления')}\n\n"
                    f"{UIEmojis.ERROR} <b>Все серверы временно недоступны!</b>\n\n"
                    f"{UIStyles.description('Не удалось найти ключ для продления. Попробуйте позже.')}"
                )
                keyboard = InlineKeyboardMarkup([
                    [UIButtons.back_button()]
                ])
                await safe_edit_or_reply_universal(query.message, error_message, reply_markup=keyboard, parse_mode="HTML", menu_type='extend_key')
                return
            
            # Ищем ключ, который соответствует short_id
            for client in all_clients:
                email = client['email']
                # Проверяем разные форматы short_id
                possible_short_ids = [
                    hashlib.md5(f"{user_id}:{email}".encode()).hexdigest()[:8],
                    hashlib.md5(f"extend:{email}".encode()).hexdigest()[:8]
                ]
                
                if short_id in possible_short_ids:
                    key_email = email
                    # Добавляем в кэш для будущих использований
                    extension_keys_cache[short_id] = {
                        'email': email,
                        'created_at': datetime.datetime.now().timestamp()
                    }
                    logger.info(f"Найден ключ по short_id: {short_id} -> {email}")
                    break
            
            if not key_email:
                # Если есть недоступные серверы, сообщаем об этом
                if unavailable_servers:
                    error_message = (
                        f"{UIStyles.header('Ошибка продления')}\n\n"
                        f"{UIEmojis.ERROR} <b>Ключ не найден</b>\n\n"
                        f"{UIEmojis.WARNING} Некоторые серверы недоступны: {', '.join(unavailable_servers)}\n\n"
                        f"{UIStyles.description('Ключ не найден на доступных серверах.')}"
                    )
                else:
                    error_message = f"{UIEmojis.ERROR} Ключ не найден"
                await safe_edit_or_reply(query.message, error_message, parse_mode="HTML" if unavailable_servers else None)
                logger.error(f"Не найден key_email для short_id: {short_id}")
                return
                
        except Exception as e:
            logger.error(f"Ошибка поиска ключа по short_id: {e}")
            error_message = (
                f"{UIStyles.header('Ошибка продления')}\n\n"
                f"{UIEmojis.ERROR} <b>Ошибка при поиске ключа</b>\n\n"
                f"{UIStyles.description('Попробуйте позже или обратитесь в поддержку.')}"
            )
            await safe_edit_or_reply(query.message, error_message, parse_mode="HTML")
            return
    
    logger.info(f"Запрос на продление ключа: user_id={user_id}, key_email={key_email}")
    
    # Проверяем, что ключ принадлежит пользователю
    if not (key_email.startswith(f"{user_id}_") or key_email.startswith(f"trial_{user_id}_")):
        await safe_edit_or_reply(query.message, f"{UIEmojis.ERROR} Ошибка: ключ не принадлежит вам.")
        return
    
    # Проверяем, что ключ существует на серверах
    try:
        xui, server_name = server_manager.find_client_on_any_server(key_email)
        if not xui or not server_name:
            await safe_edit_or_reply(query.message, "❌ Ключ не найден на серверах.")
            return
    except Exception as e:
        logger.error(f"Ошибка поиска ключа для продления: {e}")
        await safe_edit_or_reply(query.message, "❌ Ошибка при поиске ключа.")
        return
    
    # Создаем короткий идентификатор для ключа
    short_id = hashlib.md5(f"{user_id}:{key_email}".encode()).hexdigest()[:8]
    extension_keys_cache[short_id] = {
        'email': key_email,
        'created_at': datetime.datetime.now().timestamp()
    }
    logger.info(f"Создан короткий ID для продления: {short_id} -> {key_email}")
    
    # Показываем меню выбора периода продления
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("1 месяц - 150₽", callback_data=f"ext_per:month:{short_id}")],
        [InlineKeyboardButton("3 месяца - 350₽", callback_data=f"ext_per:3month:{short_id}")],
        [InlineKeyboardButton(f"{UIEmojis.PREV} Назад к ключам", callback_data=CallbackData.MYKEYS_MENU)]
    ])
    
    message_text = (
        f"{UIStyles.header('Продление ключа')}\n\n"
        f"<b>Ключ:</b> <code>{key_email}</code>\n"
        f"<b>Сервер:</b> {server_name}\n\n"
        f"{UIStyles.description('Выберите период продления:')}"
    )
    
    await safe_edit_or_reply_universal(query.message, message_text, reply_markup=keyboard, parse_mode="HTML", menu_type='extend_key')

