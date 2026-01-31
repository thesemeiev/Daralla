"""
Валидаторы и проверки
"""
import logging
from telegram import Update
from .message_helpers import safe_edit_or_reply
from .ui import UIEmojis

logger = logging.getLogger(__name__)


async def check_private_chat(update: Update) -> bool:
    """
    Проверяет, что команда используется в приватном чате.
    Возвращает True если чат приватный, False если нет.
    """
    if update.effective_chat.type != 'private':
        await safe_edit_or_reply(
            update.message,
            f"{UIEmojis.WARNING} Эта команда работает только в личных сообщениях.\n"
            f"Откройте приложение для управления подписками.",
            parse_mode="HTML"
        )
        return False
    return True

