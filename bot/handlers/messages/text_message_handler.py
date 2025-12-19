"""
Обработчик текстовых сообщений для переименования подписок
"""
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from ...utils import (
    UIEmojis, UIStyles, UIButtons,
    safe_edit_message_with_photo, safe_edit_or_reply_universal,
    check_private_chat
)
from ...navigation import CallbackData, NavigationBuilder
from ...db.subscribers_db import update_subscription_name, get_all_active_subscriptions_by_user

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
    
    user_id = str(update.message.from_user.id)
    new_name = update.message.text.strip()
    
    # Проверяем, идет ли переименование подписки
    subscription_id = context.user_data.get('rename_subscription_id')
    if subscription_id:
        # Переименование подписки
        await handle_rename_subscription(update, context, subscription_id, new_name)
        return
    
    # Старая логика переименования ключей удалена - теперь работаем только с подписками


async def handle_rename_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE, subscription_id: int, new_name: str):
    """Обрабатывает переименование подписки"""
    try:
        user_id = str(update.effective_user.id)
        
        # Проверяем, что подписка принадлежит пользователю
        from ...db.subscribers_db import get_subscription_by_id
        sub = await get_subscription_by_id(subscription_id, user_id)
        
        if not sub:
            logger.error(f"Попытка переименовать чужую подписку: user_id={user_id}, subscription_id={subscription_id}")
            # Получаем данные из контекста для сообщения об ошибке
            message_id = context.user_data.get('rename_subscription_message_id')
            chat_id = context.user_data.get('rename_subscription_chat_id')
            if message_id and chat_id:
                error_message = (
                    f"{UIStyles.header('Переименование подписки')}\n\n"
                    f"{UIEmojis.ERROR} <b>Ошибка:</b> Подписка не найдена или не принадлежит вам!\n\n"
                    f"{UIStyles.description('Попробуйте выбрать подписку из списка.')}"
                )
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data=CallbackData.SUBSCRIPTIONS_MENU)]
                ])
                await safe_edit_message_with_photo(
                    context.bot,
                    chat_id=chat_id,
                    message_id=message_id,
                    text=error_message,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    menu_type='subs_menu'
                )
            return
        
        # Удаляем сообщение пользователя
        try:
            await update.message.delete()
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение пользователя: {e}")
        
        # Получаем данные из контекста
        message_id = context.user_data.get('rename_subscription_message_id')
        chat_id = context.user_data.get('rename_subscription_chat_id')
        
        if not message_id or not chat_id:
            logger.error("Не найдены message_id или chat_id в контексте для переименования подписки")
            return
        
        # Валидация имени
        if len(new_name) > 50:
            error_message = (
                f"{UIStyles.header('Переименование подписки')}\n\n"
                f"{UIEmojis.ERROR} <b>Ошибка:</b> Имя подписки слишком длинное!\n\n"
                f"{UIStyles.description('Максимум 50 символов. Попробуйте еще раз.')}"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{UIEmojis.BACK} Отмена", callback_data=CallbackData.SUBSCRIPTIONS_MENU)]
            ])
            await safe_edit_message_with_photo(
                context.bot,
                chat_id=chat_id,
                message_id=message_id,
                text=error_message,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type='subs_menu'
            )
            return
        
        if not new_name or not new_name.strip():
            error_message = (
                f"{UIStyles.header('Переименование подписки')}\n\n"
                f"{UIEmojis.ERROR} <b>Ошибка:</b> Имя не может быть пустым!\n\n"
                f"{UIStyles.description('Введите корректное имя для подписки.')}"
            )
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{UIEmojis.BACK} Отмена", callback_data=CallbackData.SUBSCRIPTIONS_MENU)]
            ])
            await safe_edit_message_with_photo(
                context.bot,
                chat_id=chat_id,
                message_id=message_id,
                text=error_message,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type='subs_menu'
            )
            return
        
        # Обновляем имя подписки в БД
        await update_subscription_name(subscription_id, new_name.strip())
        
        # Очищаем состояние
        context.user_data.pop('rename_subscription_id', None)
        context.user_data.pop('rename_subscription_message_id', None)
        context.user_data.pop('rename_subscription_chat_id', None)
        
        # Показываем успешное сообщение
        success_message = (
            f"{UIStyles.header('Переименование подписки')}\n\n"
            f"{UIEmojis.SUCCESS} <b>Подписка успешно переименована!</b>\n\n"
            f"<b>Новое имя:</b> {new_name.strip()}\n\n"
            f"{UIStyles.description('Имя будет отображаться в списке ваших подписок.')}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Мои подписки", callback_data=CallbackData.SUBSCRIPTIONS_MENU)],
            [NavigationBuilder.create_back_button()]
        ])
        
        await safe_edit_message_with_photo(
            context.bot,
            chat_id=chat_id,
            message_id=message_id,
            text=success_message,
            reply_markup=keyboard,
            parse_mode="HTML",
            menu_type='subs_menu'
        )
        
    except Exception as e:
        logger.error(f"Ошибка при переименовании подписки: {e}")
        error_message = (
            f"{UIStyles.header('Переименование подписки')}\n\n"
            f"{UIEmojis.ERROR} <b>Ошибка:</b> {str(e)}"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data=CallbackData.SUBSCRIPTIONS_MENU)]
        ])
        try:
            message_id = context.user_data.get('rename_subscription_message_id')
            chat_id = context.user_data.get('rename_subscription_chat_id')
            if message_id and chat_id:
                await safe_edit_message_with_photo(
                    context.bot,
                    chat_id=chat_id,
                    message_id=message_id,
                    text=error_message,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    menu_type='subs_menu'
                )
        except Exception as edit_e:
            logger.error(f"Ошибка редактирования сообщения: {edit_e}")

