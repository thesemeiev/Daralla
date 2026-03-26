"""Payment webhook idempotency event log."""

DESCRIPTION = "Add payment_webhook_events table for durable idempotency"


async def up(db):
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
