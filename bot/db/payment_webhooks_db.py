"""Durable idempotency log for inbound payment webhooks."""

from __future__ import annotations

import aiosqlite

from . import DB_PATH


async def init_payment_webhooks_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS payment_webhook_events (
                event_key TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                payment_id TEXT NOT NULL,
                status TEXT NOT NULL,
                state TEXT NOT NULL,
                last_error TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        await db.commit()


async def begin_webhook_event(event_key: str, provider: str, payment_id: str, status: str, now_ts: int) -> bool:
    """
    Insert-first idempotency lock.
    Returns True if this worker should process event, False if duplicate.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """
                INSERT INTO payment_webhook_events
                (event_key, provider, payment_id, status, state, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'processing', ?, ?)
                """,
                (event_key, provider, payment_id, status, now_ts, now_ts),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def mark_webhook_event_done(event_key: str, now_ts: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE payment_webhook_events SET state = 'done', updated_at = ?, last_error = NULL WHERE event_key = ?",
            (now_ts, event_key),
        )
        await db.commit()


async def mark_webhook_event_failed(event_key: str, error_text: str, now_ts: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE payment_webhook_events SET state = 'failed', updated_at = ?, last_error = ? WHERE event_key = ?",
            (now_ts, (error_text or "")[:2000], event_key),
        )
        await db.commit()
