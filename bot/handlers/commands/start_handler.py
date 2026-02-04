"""
Обработчик команды /start
"""
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from telegram.ext import ContextTypes

from ...utils import (
    UIStyles, UIButtons, UIMessages, get_site_urls,
    safe_edit_or_reply_universal, check_private_chat
)
from ...navigation import MenuTypes
from ...db.accounts_db import (
    get_or_create_account_for_telegram,
    link_telegram_consume_state,
    get_account_id_by_identity,
    link_identity,
    get_telegram_id_for_account,
)
import time

logger = logging.getLogger(__name__)

def get_globals():
    """Получает сервисы и настройки из контекста приложения."""
    from ...context import get_app_context
    ctx = get_app_context()
    if ctx is None:
        from ..webhooks.webhook_auth import get_bot_module, get_server_manager, get_subscription_manager
        bot_module = get_bot_module()
        return {
            "server_manager": get_server_manager(),
            "subscription_manager": get_subscription_manager(),
            "WEBAPP_URL": getattr(bot_module, "WEBAPP_URL", None) if bot_module else None,
        }
    return {
        "server_manager": ctx.server_manager,
        "subscription_manager": ctx.subscription_manager,
        "WEBAPP_URL": ctx.config.WEBAPP_URL if ctx.config else None,
    }


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    if not await check_private_chat(update):
        return
    
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if message is None:
        logger.error("main_menu: message is None")
        return

    # Обработка привязки Telegram (веб-аккаунт): /start link_<state>
    args = context.args or []
    if args and args[0].startswith("link_"):
        state = args[0][5:]
        tg_user_id = str(update.effective_user.id)
        web_user_id = await link_telegram_consume_state(state)
        if not web_user_id:
            await message.reply_text("Ссылка недействительна или истекла. Зайдите на сайт и нажмите «Привязать Telegram» снова.")
            return
        if not web_user_id.isdigit():
            await message.reply_text("Ошибка: неверный формат данных.")
            return
        account_id = int(web_user_id)
        existing_account = await get_account_id_by_identity("telegram", tg_user_id)
        if existing_account and existing_account != account_id:
            context.user_data[f"link_web_user_id_{state}"] = web_user_id
            text = (
                "Этот Telegram уже привязан к другому аккаунту.\n\n"
                "Отвязать его и привязать к текущему веб-аккаунту?"
            )
            buttons = [[
                InlineKeyboardButton("Да", callback_data=f"link_confirm_yes:{state}"),
                InlineKeyboardButton("Нет", callback_data=f"link_confirm_no:{state}")
            ]]
            await message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            return
        has_tg = await get_telegram_id_for_account(account_id)
        if has_tg:
            await message.reply_text("Аккаунт уже привязан к Telegram.")
            return
        await link_identity(account_id, "telegram", tg_user_id)
        logger.info("Привязан Telegram %s к account_id=%s", tg_user_id, account_id)
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
        await message.reply_text(text, reply_markup=keyboard)
        return

    telegram_id = str(update.effective_user.id)
    account_id = await get_or_create_account_for_telegram(telegram_id)
    was_known_user = account_id is not None  # touch_account обновляет last_seen при существующем аккаунте

    welcome_text = UIMessages.welcome_message(is_new_user=True)
    buttons = UIButtons.main_menu_buttons()
    keyboard = InlineKeyboardMarkup(buttons)
    await safe_edit_or_reply_universal(message, welcome_text, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.MAIN_MENU)

