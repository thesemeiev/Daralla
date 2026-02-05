"""
Маршруты: рассылка сообщений пользователям.
"""
import asyncio
import logging

import telegram
from flask import request, jsonify

from ...webhook_auth import authenticate_request, check_admin_access
from .....context import get_app_context
from ._common import CORS_HEADERS, options_response

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def register_broadcast_routes(bp, bot_app):
    @bp.route("/api/admin/broadcast", methods=["POST", "OPTIONS"])
    def api_admin_broadcast():
        if request.method == "OPTIONS":
            return options_response()
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({"error": "Access denied"}), 403
            data = request.get_json(silent=True) or {}
            message_text = (data.get("message") or "").strip()
            if not message_text:
                return jsonify({"error": "Message text is required"}), 400
            account_ids = data.get("account_ids", data.get("user_ids", []))  # user_ids — legacy

            from .....db import get_all_account_ids
            from .....db.accounts_db import get_telegram_chat_id_for_account
            from .....utils import UIButtons

            ctx = get_app_context()
            admin_ids = list(ctx.admin_ids) if ctx else []
            admin_set = set(str(a) for a in admin_ids)

            async def send_broadcast_async():
                if account_ids:
                    recipients = [str(aid) for aid in account_ids if str(aid) not in admin_set]
                else:
                    recipients = await get_all_account_ids()
                    recipients = [str(uid) for uid in recipients if str(uid) not in admin_set]
                total = len(recipients)
                if total == 0:
                    return {"sent": 0, "failed": 0, "total": 0}
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
                        account_id = int(user_id) if isinstance(user_id, str) and user_id.isdigit() else None
                        chat_id = await get_telegram_chat_id_for_account(account_id) if account_id else None
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
                            logger.error("Ошибка отправки пользователю %s: %s", account_id_str, e)
                            failed += 1
                    if i + batch < total:
                        await asyncio.sleep(0.1)
                return {"sent": sent, "failed": failed, "total": total}

            result = _run_async(send_broadcast_async())
            return (
                jsonify(result),
                200,
                {**CORS_HEADERS, "Content-Type": "application/json"},
            )
        except Exception as e:
            logger.error("Ошибка в /api/admin/broadcast: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500
