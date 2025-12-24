"""
Обработчик команды /admin_config
"""
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from ...utils import (
    UIEmojis, safe_edit_or_reply_universal, check_private_chat, safe_answer_callback_query
)
from ...navigation import MenuTypes, CallbackData
from ...navigation import NavigationBuilder
from ...db import get_all_config, get_config, set_config
from ...db.subscribers_db import get_promo_code, delete_promo_code, create_promo_code

logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
ADMIN_CONFIG_PROMO_WAITING = 1

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
        await safe_edit_or_reply_universal(message_obj, 'Нет доступа.', menu_type=MenuTypes.ADMIN_MENU)
        return
    
    try:
        config = await get_all_config()
        
        # Получаем активный промокод из конфигурации
        active_promo_code = await get_config('active_promo_code', None)
        active_promo_period = await get_config('active_promo_period', 'month')
        
        message = "<b>Конфигурация</b>\n\n"
        
        if config:
            for key, data in config.items():
                if key != 'active_promo_code' and key != 'active_promo_type' and key != 'active_promo_period':
                    message += f"• <b>{data['description']}:</b> {data['value']}\n"
        
        # Показываем активный промокод
        message += "\n" + "="*30 + "\n\n"
        message += "<b>Активный промокод:</b>\n"
        if active_promo_code:
            promo_info = await get_promo_code(active_promo_code)
            if promo_info:
                period_text = "1 месяц" if active_promo_period == 'month' else "3 месяца"
                uses_info = f"{promo_info['uses_count']}/{promo_info['max_uses']}" if promo_info['max_uses'] > 0 else f"{promo_info['uses_count']}/∞"
                message += f"• <b>Код:</b> <code>{active_promo_code}</code>\n"
                message += f"• <b>Период:</b> {period_text}\n"
                message += f"• <b>Использований:</b> {uses_info}\n"
                message += f"• <b>Применение:</b> Покупка и продление\n"
            else:
                message += f"• <b>Код:</b> <code>{active_promo_code}</code> (не найден в БД)\n"
        else:
            message += "• <i>Не установлен</i>\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Изменить промокод", callback_data="admin_config_change_promo")],
            [NavigationBuilder.create_back_button()]
        ])
        
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply_universal(message_obj, message, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_MENU)
        
    except Exception as e:
        logger.exception("Ошибка в admin_config")
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply_universal(message_obj, f'{UIEmojis.ERROR} Ошибка: {e}', menu_type=MenuTypes.ADMIN_MENU)


async def admin_config_change_promo_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало изменения промокода"""
    query = update.callback_query
    await safe_answer_callback_query(query)
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    # Сохраняем message_id и chat_id для последующего редактирования
    context.user_data['admin_config_message_id'] = query.message.message_id
    context.user_data['admin_config_chat_id'] = query.message.chat_id
    
    message = (
        f"<b>Изменение промокода</b>\n\n"
        f"Введите новый промокод в формате:\n"
        f"<code>КОД ПЕРИОД</code>\n\n"
        f"<b>Примеры:</b>\n"
        f"• <code>PROMO2024 month</code> - на 1 месяц\n"
        f"• <code>PROMO2024 3month</code> - на 3 месяца\n\n"
        f"<b>Периоды:</b> <code>month</code> или <code>3month</code>\n\n"
        f"<i>Промокод будет работать для покупки и продления.\n"
        f"Старый промокод будет удален из БД.</i>"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{UIEmojis.PREV} Отмена", callback_data="admin_config_change_promo_cancel")]
    ])
    
    await safe_edit_or_reply_universal(
        query.message,
        message,
        reply_markup=keyboard,
        parse_mode="HTML",
        menu_type=MenuTypes.ADMIN_MENU
    )
    
    return ADMIN_CONFIG_PROMO_WAITING


async def admin_config_change_promo_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка введенного промокода"""
    user = update.effective_user
    user_id = str(user.id)
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    if user.id not in ADMIN_IDS:
        return -1
    
    # Удаляем сообщение пользователя
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение пользователя: {e}")
    
    message_id = context.user_data.get('admin_config_message_id')
    chat_id = context.user_data.get('admin_config_chat_id')
    
    # Парсим ввод
    parts = update.message.text.strip().split()
    if len(parts) < 2:
        error_message = (
            f"<b>Ошибка</b>\n\n"
            f"Неверный формат. Используйте:\n"
            f"<code>КОД ПЕРИОД</code>\n\n"
            f"Пример: <code>PROMO2024 month</code>"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.PREV} Назад", callback_data="admin_config")]
        ])
        
        from ...utils import safe_edit_message_with_photo
        try:
            await safe_edit_message_with_photo(
                context.bot,
                chat_id=chat_id,
                message_id=message_id,
                text=error_message,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type=MenuTypes.ADMIN_MENU
            )
        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")
        
        # Очищаем контекст
        context.user_data.pop('admin_config_message_id', None)
        context.user_data.pop('admin_config_chat_id', None)
        return -1
    
    promo_code = parts[0].upper()
    promo_period = parts[1].lower()
    
    if promo_period not in ['month', '3month']:
        error_message = (
            f"<b>Ошибка</b>\n\n"
            f"Неверный период. Используйте: <code>month</code> или <code>3month</code>"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.PREV} Назад", callback_data="admin_config")]
        ])
        
        from ...utils import safe_edit_message_with_photo
        try:
            await safe_edit_message_with_photo(
                context.bot,
                chat_id=chat_id,
                message_id=message_id,
                text=error_message,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type=MenuTypes.ADMIN_MENU
            )
        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")
        
        context.user_data.pop('admin_config_message_id', None)
        context.user_data.pop('admin_config_chat_id', None)
        return -1
    
    try:
        # Получаем старый промокод из конфигурации
        old_promo_code = await get_config('active_promo_code', None)
        
        # Удаляем старый промокод из БД (если был)
        if old_promo_code:
            await delete_promo_code(old_promo_code)
            logger.info(f"Удален старый промокод: {old_promo_code}")
        
        # Создаем новый промокод в БД для покупки (безлимитный, без срока действия)
        await create_promo_code(
            code=promo_code,
            promo_type='purchase',  # Создаем для покупки, но промокод будет работать и для продления
            period=promo_period,
            max_uses=0,  # Безлимитный
            expires_at=None  # Без срока действия
        )
        
        # Обновляем конфигурацию (убираем тип, так как промокод универсальный)
        await set_config('active_promo_code', promo_code, 'Активный промокод')
        await set_config('active_promo_period', promo_period, 'Период активного промокода')
        
        logger.info(f"Активный промокод изменен: {old_promo_code} -> {promo_code}")
        
        # Показываем успешное сообщение
        success_message = (
            f"<b>✅ Промокод изменен</b>\n\n"
            f"<b>Новый промокод:</b> <code>{promo_code}</code>\n"
            f"<b>Период:</b> {'1 месяц' if promo_period == 'month' else '3 месяца'}\n"
            f"<b>Применение:</b> Покупка и продление\n\n"
            f"{'Старый промокод удален из БД.' if old_promo_code else ''}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Конфигурация", callback_data="admin_config")]
        ])
        
        from ...utils import safe_edit_message_with_photo
        try:
            await safe_edit_message_with_photo(
                context.bot,
                chat_id=chat_id,
                message_id=message_id,
                text=success_message,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type=MenuTypes.ADMIN_MENU
            )
        except Exception as e:
            logger.error(f"Ошибка редактирования сообщения: {e}")
            await safe_edit_or_reply_universal(
                update.message,
                success_message,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type=MenuTypes.ADMIN_MENU
            )
        
    except Exception as e:
        logger.exception(f"Ошибка изменения промокода: {e}")
        error_message = (
            f"<b>❌ Ошибка</b>\n\n"
            f"Не удалось изменить промокод: {str(e)}"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.PREV} Назад", callback_data="admin_config")]
        ])
        
        from ...utils import safe_edit_message_with_photo
        try:
            await safe_edit_message_with_photo(
                context.bot,
                chat_id=chat_id,
                message_id=message_id,
                text=error_message,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type=MenuTypes.ADMIN_MENU
            )
        except Exception as edit_e:
            logger.error(f"Ошибка редактирования сообщения: {edit_e}")
    
    # Очищаем контекст
    context.user_data.pop('admin_config_message_id', None)
    context.user_data.pop('admin_config_chat_id', None)
    
    return -1


async def admin_config_change_promo_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена изменения промокода"""
    query = update.callback_query
    if query:
        await safe_answer_callback_query(query)
    
    # Очищаем контекст
    context.user_data.pop('admin_config_message_id', None)
    context.user_data.pop('admin_config_chat_id', None)
    
    # Возвращаемся в конфигурацию
    await admin_config(update, context)
    
    return -1

