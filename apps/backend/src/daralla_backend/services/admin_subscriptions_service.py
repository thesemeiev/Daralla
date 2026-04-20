"""Service helpers for admin subscriptions routes."""

from __future__ import annotations

import aiosqlite

from bot.db import DB_PATH


async def get_user_id_from_subscriber_id(subscriber_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT user_id FROM users WHERE id = ?", (subscriber_id,)) as cur:
            row = await cur.fetchone()
            return row["user_id"] if row else None


async def get_user_id_from_subscription_id(sub_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT u.user_id FROM users u JOIN subscriptions s ON u.id = s.subscriber_id WHERE s.id = ?",
            (sub_id,),
        ) as cur:
            row = await cur.fetchone()
            return row["user_id"] if row else ""


async def delete_subscription_record(sub_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
        await db.commit()
