"""
Обработчик callback для подтверждения привязки Telegram к веб-аккаунту
"""
import logging
import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from telegram.ext import ContextTypes

from ...utils import safe_answer_callback_query, check_private_chat
from ...db.subscribers_db import (
    link_telegram_consume_state, get_user_by_id, update_user_telegram_id,
    orphan_telegram_first_user_and_create_placeholder
)

logger = logging.getLogger(__name__)


async def link_telegram_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback для подтверждения привязки Telegram (Да/Нет)"""
    if not await check_private_chat(update):
        return
    
    query = update.callback_query
    if not query:
        return
    
    await safe_answer_callback_query(query)
    
    # Парсим callback_data: link_confirm_yes:<state> или link_confirm_no:<state>
    callback_data = query.data
    if not callback_data.startswith("link_confirm_"):
        return
    
    is_yes = callback_data.startswith("link_confirm_yes:")
    state = callback_data.split(":", 1)[1] if ":" in callback_data else None
    
    if not state:
        await query.message.reply_text("Ошибка: неверный формат данных.")
        return
    
    tg_user_id = str(update.effective_user.id)
    message = query.message
    
    if not is_yes:
        # Пользователь нажал "Нет" - отменяем привязку
        await query.message.edit_text("Привязка отменена.")
        return
    
    # Пользователь нажал "Да" - выполняем привязку
    try:
        # Получаем web_user_id из контекста (сохранен в start_handler)
        web_user_id = context.user_data.get(f"link_web_user_id_{state}")
        
        if not web_user_id:
            await query.message.edit_text("Ошибка: данные привязки устарели. Зайдите на сайт и нажмите «Привязать Telegram» снова.")
            return
        
        # Проверяем веб-пользователя
        web_user = await get_user_by_id(web_user_id)
        if not web_user or not web_user.get("is_web"):
            await query.message.edit_text("Ошибка: веб-аккаунт не найден.")
            return
        
        if web_user.get("telegram_id"):
            await query.message.edit_text("Аккаунт уже привязан к Telegram.")
            return
        
        # Осирочиваем TG-first пользователя (если есть) и создаем placeholder
        orphan_result = await orphan_telegram_first_user_and_create_placeholder(tg_user_id)
        
        # Привязываем Telegram к веб-аккаунту
        await update_user_telegram_id(web_user_id, tg_user_id)
        
        logger.info(
            f"Привязан Telegram {tg_user_id} к веб-аккаунту {web_user_id} "
            f"(после подтверждения). Осирочен: {orphan_result.get('orphaned')}"
        )
        
        # Удаляем временные данные из контекста
        context.user_data.pop(f"link_web_user_id_{state}", None)
        
        text = (
            "Аккаунт привязан.\n\n"
            "Теперь вы можете:\n"
            "• Заходить в Mini App без пароля\n"
            "• Получать уведомления о подписках в этом чате"
        )
        buttons = []
        webapp_url = os.getenv("WEBAPP_URL", "").strip()
        if webapp_url:
            buttons.append([InlineKeyboardButton("Открыть Mini App", web_app=WebAppInfo(url=webapp_url))])
        site_url = os.getenv("WEBSITE_URL", "").strip()
        if site_url:
            buttons.append([InlineKeyboardButton("Вернуться на сайт", url=site_url)])
        keyboard = InlineKeyboardMarkup(buttons) if buttons else None
        
        await query.message.edit_text(text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Ошибка при привязке Telegram: {e}", exc_info=True)
        await query.message.edit_text("Произошла ошибка при привязке. Попробуйте позже или обратитесь в поддержку.")
