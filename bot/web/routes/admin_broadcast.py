"""
Quart Blueprint: POST /api/admin/broadcast (broadcast message to users).
"""
import asyncio
import logging

import telegram
from quart import Blueprint, request, jsonify

from bot.web.routes.admin_common import _cors_headers, admin_route
from bot.db import get_all_user_ids
from bot.db.users_db import get_telegram_chat_id_for_notification
from bot.handlers.api_support.webhook_auth import get_bot_module
from bot.utils import UIButtons

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint("admin_broadcast", __name__)

    @bp.route("/api/admin/broadcast", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_broadcast(request, admin_id):
        data = await request.get_json(silent=True) or {}
        message_text = (data.get("message") or "").strip()
        if not message_text:
            return jsonify({"error": "Message text is required"}), 400, _cors_headers()

        user_ids = data.get("user_ids", [])
        bot_module = get_bot_module()
        ADMIN_IDS = getattr(bot_module, "ADMIN_IDS", []) if bot_module else []
        admin_set = set(str(a) for a in ADMIN_IDS)

        if user_ids:
            recipients = [str(uid) for uid in user_ids if str(uid) not in admin_set]
        else:
            all_ids = await get_all_user_ids()
            recipients = [str(uid) for uid in all_ids if str(uid) not in admin_set]

        total = len(recipients)
        if total == 0:
            return jsonify({"sent": 0, "failed": 0, "total": 0}), 200, _cors_headers()

        sent = 0
        failed = 0
        batch = 40
        webapp_button = UIButtons.create_webapp_button(text="Открыть в приложении")
        reply_markup = None
        if webapp_button:
            from telegram import InlineKeyboardMarkup
            reply_markup = InlineKeyboardMarkup([[webapp_button]])
        bot = bot_app.bot

        sent_chat_ids = set()
        for i in range(0, total, batch):
            chunk = recipients[i : i + batch]
            for user_id in chunk:
                chat_id = await get_telegram_chat_id_for_notification(user_id)
                if chat_id is None:
                    continue
                if chat_id in sent_chat_ids:
                    continue
                sent_chat_ids.add(chat_id)
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=message_text,
                        parse_mode="HTML",
                        disable_web_page_preview=True,
                        reply_markup=reply_markup,
                    )
                    sent += 1
                except telegram.error.Forbidden:
                    failed += 1
                except telegram.error.BadRequest:
                    failed += 1
                except telegram.error.RetryAfter as e:
                    await asyncio.sleep(int(getattr(e, "retry_after", 1)))
                    try:
                        await bot.send_message(
                            chat_id=chat_id,
                            text=message_text,
                            parse_mode="HTML",
                            disable_web_page_preview=True,
                            reply_markup=reply_markup,
                        )
                        sent += 1
                    except Exception:
                        failed += 1
                except Exception as e:
                    logger.error("Ошибка отправки сообщения пользователю %s: %s", user_id, e)
                    failed += 1
            if i + batch < total:
                await asyncio.sleep(0.1)

        return jsonify({"sent": sent, "failed": failed, "total": total}), 200, _cors_headers()

    return bp
