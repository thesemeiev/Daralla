"""
Админ команда для проверки подписки по токену
"""
import logging
import datetime
from telegram import Update
from telegram.ext import ContextTypes

from ...bot import ADMIN_IDS
from ...db.subscribers_db import get_subscription_by_token, get_subscription_servers
from ...utils import UIEmojis, UIStyles

logger = logging.getLogger(__name__)


async def admin_check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверяет подписку по токену"""
    user = update.effective_user
    
    if user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа к этой команде")
        return
    
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            f"{UIStyles.header('Проверка подписки')}\n\n"
            f"Использование: /admin_check_subscription <token>\n\n"
            f"Пример: /admin_check_subscription 1b97286f426a4d0687fdc3c3"
        )
        return
    
    token = context.args[0]
    
    try:
        import asyncio
        sub = await get_subscription_by_token(token)
        
        if not sub:
            await update.message.reply_text(
                f"{UIEmojis.ERROR} Подписка с токеном `{token}` не найдена",
                parse_mode="Markdown"
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
        if webhook_url:
            subscription_url = f"{webhook_url}/sub/{token}"
            message += f"\n<b>Subscription URL:</b>\n<code>{subscription_url}</code>"
        else:
            message += f"\n{UIEmojis.WARNING} <b>WEBHOOK_URL не установлен!</b>"
        
        await update.message.reply_text(message, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Ошибка в admin_check_subscription: {e}", exc_info=True)
        await update.message.reply_text(
            f"{UIEmojis.ERROR} Ошибка при проверке подписки: {str(e)}"
        )

