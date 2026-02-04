"""
Обработчик callback для подтверждения привязки Telegram к веб-аккаунту
"""
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from telegram.ext import ContextTypes

from ...utils import safe_answer_callback_query, check_private_chat, get_site_urls
from ...db.accounts_db import (
    link_telegram_consume_state,
    link_identity,
    get_telegram_id_for_account,
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
        web_user_id = context.user_data.get(f"link_web_user_id_{state}")
        if not web_user_id or not web_user_id.isdigit():
            await query.message.edit_text("Ошибка: данные привязки устарели. Зайдите на сайт и нажмите «Привязать Telegram» снова.")
            return
        account_id = int(web_user_id)
        has_tg = await get_telegram_id_for_account(account_id)
        if has_tg:
            await query.message.edit_text("Аккаунт уже привязан к Telegram.")
            return
        await link_identity(account_id, "telegram", tg_user_id)
        logger.info("Привязан Telegram %s к account_id=%s (после подтверждения)", tg_user_id, account_id)

        # Удаляем временные данные из контекста
        context.user_data.pop(f"link_web_user_id_{state}", None)
        
        text = (
            "Аккаунт привязан.\n\n"
            "Теперь вы можете:\n"
            "• Заходить в Mini App без пароля\n"
            "• Получать уведомления о подписках в этом чате"
        )
        buttons = []
        webapp_url, site_url = get_site_urls()
        if webapp_url:
            buttons.append([InlineKeyboardButton("Открыть Mini App", web_app=WebAppInfo(url=webapp_url))])
        if site_url:
            buttons.append([InlineKeyboardButton("Вернуться на сайт", url=site_url)])
        keyboard = InlineKeyboardMarkup(buttons) if buttons else None
        
        await query.message.edit_text(text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Ошибка при привязке Telegram: {e}", exc_info=True)
        await query.message.edit_text("Произошла ошибка при привязке. Попробуйте позже или обратитесь в поддержку.")
