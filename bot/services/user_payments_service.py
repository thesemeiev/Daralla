"""Service helpers for user payment routes."""

from __future__ import annotations

import aiosqlite

from bot.db import DB_PATH, add_payment, get_payment_by_id
from bot.db.subscriptions_db import get_subscription_by_id


async def get_user_subscription_for_extension(subscription_id: int, user_id: str):
    return await get_subscription_by_id(subscription_id, user_id)


async def cancel_pending_user_payments(user_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE payments SET status = ? WHERE user_id = ? AND status = ?",
            ("canceled", user_id, "pending"),
        )
        await db.commit()


async def create_pending_payment(payment_id: str, user_id: str, meta: dict) -> None:
    await add_payment(payment_id=payment_id, user_id=user_id, status="pending", meta=meta)


async def fetch_payment_by_id(payment_id: str):
    return await get_payment_by_id(payment_id)
