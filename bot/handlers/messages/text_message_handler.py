"""
Обработчик текстовых сообщений для переименования ключей
"""
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from ...utils import (
    UIEmojis, UIStyles, UIButtons,
    safe_edit_message_with_photo, check_private_chat
)
from ...navigation import CallbackData

logger = logging.getLogger(__name__)


def get_globals():
    """Получает глобальные переменные из bot.py"""
    try:
        import sys
        import importlib
        # Пытаемся получить модуль bot.bot
        if 'bot.bot' in sys.modules:
            bot_module = sys.modules['bot.bot']
        else:
            # Если модуль еще не загружен, импортируем его
            bot_module = importlib.import_module('bot.bot')
        
        return {
            'server_manager': getattr(bot_module, 'server_manager', None),
        }
    except (ImportError, AttributeError) as e:
        logger.warning(f"Не удалось получить глобальные переменные: {e}")
        return {
            'server_manager': None,
        }


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    if not await check_private_chat(update):
        return
    
    # Функционал переименования ключей удален
    # Оставляем функцию для совместимости, но она ничего не делает
    return
    
    user_id = str(update.message.from_user.id)
    new_name = update.message.text.strip()
    
    # Удаляем сообщение пользователя
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение пользователя: {e}")
    
    # Получаем данные из контекста
    message_id = context.user_data.get('rename_message_id')
    chat_id = context.user_data.get('rename_chat_id')
    
    if not message_id or not chat_id:
        logger.error("Не найдены message_id или chat_id в контексте")
        return
    
    # Данные для редактирования сообщения получены из контекста
    
    # Валидация имени
    if len(new_name) > 50:
        error_message = (
            f"{UIStyles.header('Переименование ключа')}\n\n"
            f"{UIEmojis.ERROR} <b>Ошибка:</b> Имя ключа слишком длинное!\n\n"
            f"{UIStyles.description('Максимум 50 символов. Попробуйте еще раз.')}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [UIButtons.back_button()]
        ])
        
        try:
            # Редактируем сообщение через бота
            await safe_edit_message_with_photo(
                context.bot,
                chat_id=chat_id,
                message_id=message_id,
                text=error_message,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type='extend_key'
            )
        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")
        return
    
    # Получаем email ключа из контекста
    key_email = context.user_data.get('rename_key_email')
    
    if not key_email:
        error_message = (
            f"{UIStyles.header('Переименование ключа')}\n\n"
            f"{UIEmojis.ERROR} <b>Ошибка:</b> Ключ не найден в контексте!"
        )
        
        keyboard = InlineKeyboardMarkup([
            [UIButtons.back_button()]
        ])
        
        try:
            await safe_edit_message_with_photo(
                context.bot,
                chat_id=chat_id,
                message_id=message_id,
                text=error_message,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type='extend_key'
            )
        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")
        return
    
    # Получаем глобальные переменные
    globals_dict = get_globals()
    server_manager = globals_dict['server_manager']
    
    if not server_manager:
        error_message = (
            f"{UIStyles.header('Переименование ключа')}\n\n"
            f"{UIEmojis.ERROR} <b>Ошибка:</b> Серверы не настроены!"
        )
        keyboard = InlineKeyboardMarkup([
            [UIButtons.back_button()]
        ])
        try:
            await safe_edit_message_with_photo(
                context.bot,
                chat_id=chat_id,
                message_id=message_id,
                text=error_message,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type='extend_key'
            )
        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")
        return
    
    # Находим сервер с ключом
    try:
        xui, server_name = server_manager.find_client_on_any_server(key_email)
        if not xui or not server_name:
            error_message = (
                f"{UIStyles.header('Переименование ключа')}\n\n"
                f"{UIEmojis.ERROR} <b>Ошибка:</b> Ключ не найден на серверах!"
            )
            
            keyboard = InlineKeyboardMarkup([
                [UIButtons.back_button()]
            ])
            
            try:
                await safe_edit_message_with_photo(
                    context.bot,
                    chat_id=chat_id,
                    message_id=message_id,
                    text=error_message,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    menu_type='extend_key'
                )
            except Exception as e:
                logger.error(f"Ошибка редактирования сообщения: {e}")
            return
        
        # Обновляем имя ключа
        try:
            response = xui.updateClientName(key_email, new_name)
        except Exception as e:
            logger.error(f"Ошибка переименования ключа {key_email} на сервере {server_name}: {e}")
            error_message = (
                f"{UIStyles.header('Переименование ключа')}\n\n"
                f"{UIEmojis.ERROR} <b>Ошибка:</b> Не удалось переименовать ключ!\n\n"
                f"<b>Причина:</b> Сервер временно недоступен\n\n"
                f"{UIStyles.description('Попробуйте позже')}"
            )
            keyboard = InlineKeyboardMarkup([
                [UIButtons.back_button()]
            ])
            try:
                await safe_edit_message_with_photo(
                    context.bot,
                    chat_id=chat_id,
                    message_id=message_id,
                    text=error_message,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    menu_type='extend_key'
                )
            except Exception as edit_e:
                logger.error(f"Ошибка редактирования сообщения: {edit_e}")
            return
        
        if response and response.status_code == 200:
            # Очищаем состояние
            context.user_data.pop('waiting_for_key_name', None)
            context.user_data.pop('rename_key_email', None)
            context.user_data.pop('rename_message_id', None)
            context.user_data.pop('rename_chat_id', None)
            
            # Показываем успешное сообщение в том же окне
            success_message = (
                f"{UIStyles.header('Переименование ключа')}\n\n"
                f"{UIEmojis.SUCCESS} <b>Ключ успешно переименован!</b>\n\n"
                f"<b>Новое имя:</b> {new_name}\n"
                f"<b>Email:</b> <code>{key_email}</code>\n\n"
                f"{UIStyles.description('Имя будет отображаться в списке ваших ключей')}"
            )
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Мои ключи", callback_data=CallbackData.MYKEYS_MENU)],
                [UIButtons.back_button()]
            ])
            
            try:
                await safe_edit_message_with_photo(
                    context.bot,
                    chat_id=chat_id,
                    message_id=message_id,
                    text=success_message,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    menu_type='extend_key'
                )
            except Exception as e:
                logger.error(f"Ошибка редактирования сообщения: {e}")
        else:
            error_message = (
                f"{UIStyles.header('Переименование ключа')}\n\n"
                f"{UIEmojis.ERROR} <b>Ошибка:</b> Не удалось обновить имя ключа на сервере!"
            )
            
            keyboard = InlineKeyboardMarkup([
                [UIButtons.back_button()]
            ])
            
            try:
                await safe_edit_message_with_photo(
                    context.bot,
                    chat_id=chat_id,
                    message_id=message_id,
                    text=error_message,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    menu_type='extend_key'
                )
            except Exception as e:
                logger.error(f"Ошибка редактирования сообщения: {e}")
    
    except Exception as e:
        logger.error(f"Ошибка при переименовании ключа: {e}")
        error_message = (
            f"{UIStyles.header('Переименование ключа')}\n\n"
            f"{UIEmojis.ERROR} <b>Ошибка:</b> {str(e)}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [UIButtons.back_button()]
        ])
        
        try:
            await safe_edit_message_with_photo(
                context.bot,
                chat_id=chat_id,
                message_id=message_id,
                text=error_message,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type='extend_key'
            )
        except Exception as edit_e:
            logger.error(f"Ошибка редактирования сообщения: {edit_e}")

