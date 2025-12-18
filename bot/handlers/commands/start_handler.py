"""
Обработчик команды /start
"""
import logging
import datetime
import uuid
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from ...utils import (
    UIEmojis, UIStyles, UIButtons, UIMessages,
    safe_edit_or_reply_universal, check_private_chat, format_vpn_key_message,
    check_user_has_existing_keys
)
from ...db import is_known_user, register_simple_user

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
        return {'ADMIN_IDS': [], 'new_client_manager': None, 'nav_system': None}


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
    
    # Автовыдача обычного ключа на 14 дней новому клиенту (по БД реф. системы)
    if new_client_manager:
        try:
            user_id_str = str(update.effective_user.id)
            is_new = not await is_known_user(user_id_str)
            
            # Проверяем, есть ли у пользователя существующие ключи на серверах
            has_existing_keys = await check_user_has_existing_keys(user_id_str, new_client_manager)
            
            if is_new and not has_existing_keys:
                try:
                    xui, server_name = new_client_manager.get_best_location_server()
                except Exception as server_error:
                    logger.warning(f"Не удалось получить сервер для бесплатного ключа пользователя {user_id_str}: {server_error}")
                    xui, server_name = None, None
                
                if not xui or not server_name:
                    logger.warning(f"Не удалось получить сервер для бесплатного ключа пользователя {user_id_str}")
                    # Уведомляем пользователя, что серверы недоступны
                    welcome_text += "\n\n" + UIStyles.warning_message(
                        "⚠️ В данный момент все серверы временно недоступны.\n"
                        "Бесплатный ключ будет выдан автоматически, как только серверы станут доступны.\n\n"
                        "Попробуйте позже или обратитесь в поддержку."
                    )
                else:
                    unique_email = f"{user_id_str}_{uuid.uuid4()}"
                    try:
                        response = xui.addClient(day=14, tg_id=user_id_str, user_email=unique_email, timeout=15)
                        # Проверяем не только HTTP статус, но и поле success в JSON
                        is_success = False
                        if response and getattr(response, 'status_code', None) == 200:
                            try:
                                import json
                                response_json = response.json()
                                is_success = response_json.get('success', False)
                                if not is_success:
                                    error_msg = response_json.get('msg', 'Unknown error')
                                    logger.error(f"Не удалось создать бесплатный ключ: {error_msg}")
                            except (json.JSONDecodeError, ValueError, AttributeError):
                                # Если ответ не JSON, считаем успешным только если статус 200
                                is_success = True
                        
                        if is_success:
                            try:
                                # Передаем название сервера для tag в ссылке
                                link = xui.link(unique_email, server_name=server_name)
                            except Exception as link_e:
                                logger.error(f"Ошибка получения ссылки на ключ: {link_e}")
                                link = "Ошибка получения ссылки"
                            expiry_time = datetime.datetime.now() + datetime.timedelta(days=14)
                            expiry_str = expiry_time.strftime('%d.%m.%Y %H:%M')
                            expiry_ts = int(expiry_time.timestamp())
                            welcome_text += "\n\n" + UIStyles.info_message("Вам выдан бесплатный ключ на 14 дней") + "\n\n"
                            welcome_text += format_vpn_key_message(
                                email=unique_email,
                                status='Активен',
                                server=server_name,
                                expiry=expiry_str,
                                key=link,
                                expiry_timestamp=expiry_ts
                            )
                    except Exception as create_e:
                        logger.error(f"Ошибка создания бесплатного ключа для пользователя {user_id_str}: {create_e}")
            elif is_new and has_existing_keys:
                logger.info(f"Пользователь {user_id_str} новый в БД, но уже имеет ключи на серверах - пропускаем выдачу")
            elif not is_new:
                logger.info(f"Пользователь {user_id_str} уже известен в БД - пропускаем выдачу")
        except Exception as e:
            logger.error(f"START free key issue error: {e}")

    # Теперь, когда все проверки выполнены, регистрируем пользователя
    try:
        await register_simple_user(user_id)
    except Exception as e:
        logger.error(f"Register user failed: {e}")
    
    # Добавляем главное меню в навигационный стек при старте
    globals_dict = get_globals()
    nav_system = globals_dict.get('nav_system')
    if nav_system:
        from ...navigation import nav_manager, NavStates
        nav_manager.clear_stack(context)
        nav_manager.push_state(context, NavStates.MAIN_MENU)
    
    # Отправляем меню с фото
    await safe_edit_or_reply_universal(message, welcome_text, reply_markup=keyboard, parse_mode="HTML", menu_type='main_menu')


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
        await safe_edit_or_reply_universal(message, welcome_text, reply_markup=keyboard, parse_mode="HTML", menu_type='main_menu')
        logger.info("EDIT_MAIN_MENU: Сообщение успешно отредактировано")
    except Exception as e:
        logger.error(f"EDIT_MAIN_MENU: Ошибка редактирования сообщения: {e}")
        # Если не удалось отредактировать, отправляем новое
        logger.info("EDIT_MAIN_MENU: Вызываем start() как fallback")
        await start(update, context)

