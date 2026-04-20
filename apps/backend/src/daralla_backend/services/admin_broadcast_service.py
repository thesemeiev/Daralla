"""Service layer for admin broadcast flow."""

from __future__ import annotations

import asyncio
import logging

import telegram

from daralla_backend.app_context import get_ctx
from daralla_backend.db import get_all_user_ids
from daralla_backend.db.users_db import get_telegram_chat_id_for_notification

logger = logging.getLogger(__name__)


async def resolve_broadcast_recipients(user_ids: list | None):
    admin_ids = get_ctx().admin_ids
    admin_set = set(str(a) for a in admin_ids)
    if user_ids:
        return [str(uid) for uid in user_ids if str(uid) not in admin_set]
    all_ids = await get_all_user_ids()
    return [str(uid) for uid in all_ids if str(uid) not in admin_set]


async def send_broadcast(bot, recipients: list[str], message_text: str):
    total = len(recipients)
    if total == 0:
        return {"sent": 0, "failed": 0, "total": 0}

    sent = 0
    failed = 0
    batch = 40
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
                    )
                    sent += 1
                except Exception:
                    failed += 1
            except Exception as e:
                logger.error("Ошибка отправки сообщения пользователю %s: %s", user_id, e)
                failed += 1
        if i + batch < total:
            await asyncio.sleep(0.1)

    return {"sent": sent, "failed": failed, "total": total}
