"""
Админ команда для проверки подписки по токену
"""
import logging
import datetime
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from ...db.subscribers_db import get_subscription_by_token, get_subscription_servers
from ...utils import UIEmojis, UIStyles, safe_edit_or_reply_universal
from ...navigation import NavigationBuilder, MenuTypes

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
        return {
            'ADMIN_IDS': [],
        }


async def admin_check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверяет подписку по токену"""
    user = update.effective_user
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    
    if user.id not in ADMIN_IDS:
        await safe_edit_or_reply_universal(message_obj, "Нет доступа к этой команде", menu_type=MenuTypes.ADMIN_MENU)
        return
    
    if not context.args or len(context.args) == 0:
        keyboard = InlineKeyboardMarkup([
            [NavigationBuilder.create_back_button()]
        ])
        await safe_edit_or_reply_universal(
            message_obj,
            f"{UIStyles.header('Проверка подписки')}\n\n"
            f"Использование: /admin_check_subscription <token>\n\n"
            f"Пример: /admin_check_subscription 1b97286f426a4d0687fdc3c3",
            reply_markup=keyboard,
            menu_type=MenuTypes.ADMIN_MENU
        )
        return
    
    token = context.args[0]
    
    try:
        import asyncio
        sub = await get_subscription_by_token(token)
        
        if not sub:
            keyboard = InlineKeyboardMarkup([
                [NavigationBuilder.create_back_button()]
            ])
            await safe_edit_or_reply_universal(
                message_obj,
                f"{UIEmojis.ERROR} Подписка с токеном <code>{token}</code> не найдена",
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type=MenuTypes.ADMIN_MENU
            )
            return
        
        # Получаем серверы подписки
        servers = await get_subscription_servers(sub["id"])
        
        # Форматируем время
        created_at = datetime.datetime.fromtimestamp(sub["created_at"])
        expires_at = datetime.datetime.fromtimestamp(sub["expires_at"])
        current_time = datetime.datetime.now()
        
        # Проверяем статус
        is_expired = sub["expires_at"] < int(current_time.timestamp())
        is_active = sub["status"] == "active" and not is_expired
        
        status_emoji = UIEmojis.SUCCESS if is_active else UIEmojis.ERROR
        status_text = "Активна" if is_active else f"Неактивна (status: {sub['status']}, expired: {is_expired})"
        
        message = (
            f"{UIStyles.header('Информация о подписке')}\n\n"
            f"{status_emoji} <b>Статус:</b> {status_text}\n\n"
            f"<b>ID подписки:</b> {sub['id']}\n"
            f"<b>Пользователь:</b> {sub['user_id']}\n"
            f"<b>Токен:</b> <code>{sub['subscription_token']}</code>\n"
            f"<b>Период:</b> {sub['period']}\n"
            f"<b>Устройств:</b> {sub['device_limit']}\n"
            f"<b>Цена:</b> {sub['price']}₽\n\n"
            f"<b>Создана:</b> {created_at.strftime('%d.%m.%Y %H:%M:%S')}\n"
            f"<b>Истекает:</b> {expires_at.strftime('%d.%m.%Y %H:%M:%S')}\n"
            f"<b>Текущее время:</b> {current_time.strftime('%d.%m.%Y %H:%M:%S')}\n\n"
            f"<b>Серверов привязано:</b> {len(servers)}\n"
        )
        
        if servers:
            message += f"\n<b>Серверы:</b>\n"
            for i, server in enumerate(servers, 1):
                message += f"{i}. {server['server_name']} ({server['client_email']})\n"
        
        # Проверяем доступность subscription URL
        import os
        webhook_url = os.getenv("WEBHOOK_URL", "").rstrip("/")
        subscription_base_url = os.getenv("SUBSCRIPTION_URL", "").rstrip("/")
        
        # Если SUBSCRIPTION_URL не установлен, извлекаем базовый URL из WEBHOOK_URL
        if subscription_base_url:
            base_url = subscription_base_url
        elif webhook_url:
            from urllib.parse import urlparse
            parsed = urlparse(webhook_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
        else:
            base_url = None
        
        if base_url:
            subscription_url = f"{base_url}/sub/{token}"
            message += f"\n<b>Subscription URL:</b>\n<code>{subscription_url}</code>"
        else:
            message += f"\n{UIEmojis.WARNING} <b>WEBHOOK_URL не установлен!</b>"
        
        keyboard = InlineKeyboardMarkup([
            [NavigationBuilder.create_back_button()]
        ])
        await safe_edit_or_reply_universal(
            message_obj,
            message,
            reply_markup=keyboard,
            parse_mode="HTML",
            menu_type=MenuTypes.ADMIN_MENU
        )
        
    except Exception as e:
        logger.error(f"Ошибка в admin_check_subscription: {e}", exc_info=True)
        keyboard = InlineKeyboardMarkup([
            [NavigationBuilder.create_back_button()]
        ])
        await safe_edit_or_reply_universal(
            message_obj,
            f"{UIEmojis.ERROR} Ошибка при проверке подписки: {str(e)}",
            reply_markup=keyboard,
            menu_type=MenuTypes.ADMIN_MENU
        )

