"""
Таблицы для per-node traffic bucket лимитов подписок.
"""
import aiosqlite

DESCRIPTION = "Traffic buckets, mapping, usage, enforcement state, snapshots"


async def up(db: aiosqlite.Connection) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS subscription_traffic_buckets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            limit_bytes INTEGER NOT NULL DEFAULT 0,
            is_unlimited INTEGER NOT NULL DEFAULT 0,
            is_enabled INTEGER NOT NULL DEFAULT 1,
            window_days INTEGER NOT NULL DEFAULT 30,
            credit_periods_total INTEGER NOT NULL DEFAULT 1,
            credit_periods_remaining INTEGER NOT NULL DEFAULT 1,
            period_started_at INTEGER,
            period_ends_at INTEGER,
            created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (subscription_id) REFERENCES subscriptions(id),
            UNIQUE(subscription_id, name)
        )
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sub_traffic_buckets_subscription
        ON subscription_traffic_buckets(subscription_id, is_enabled, is_unlimited)
        """
    )

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS subscription_server_traffic_bucket_map (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER NOT NULL,
            server_name TEXT NOT NULL,
            bucket_id INTEGER NOT NULL,
            updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (subscription_id) REFERENCES subscriptions(id),
            FOREIGN KEY (bucket_id) REFERENCES subscription_traffic_buckets(id),
            UNIQUE(subscription_id, server_name)
        )
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sub_traffic_bucket_map_bucket
        ON subscription_server_traffic_bucket_map(bucket_id, subscription_id)
        """
    )

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS subscription_traffic_usage_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bucket_id INTEGER NOT NULL,
            day_utc TEXT NOT NULL,
            bytes_used INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (bucket_id) REFERENCES subscription_traffic_buckets(id),
            UNIQUE(bucket_id, day_utc)
        )
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sub_traffic_usage_day
        ON subscription_traffic_usage_daily(day_utc, bucket_id)
        """
    )

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS subscription_traffic_enforcement_state (
            bucket_id INTEGER PRIMARY KEY,
            is_exhausted INTEGER NOT NULL DEFAULT 0,
            last_checked_at INTEGER,
            last_enforced_at INTEGER,
            version INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (bucket_id) REFERENCES subscription_traffic_buckets(id)
        )
        """
    )

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS subscription_server_traffic_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER NOT NULL,
            server_name TEXT NOT NULL,
            client_email TEXT NOT NULL,
            last_up INTEGER NOT NULL DEFAULT 0,
            last_down INTEGER NOT NULL DEFAULT 0,
            captured_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (subscription_id) REFERENCES subscriptions(id),
            UNIQUE(subscription_id, server_name, client_email)
        )
        """
    )

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS subscription_traffic_adjustments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bucket_id INTEGER NOT NULL,
            day_utc TEXT NOT NULL,
            bytes_delta INTEGER NOT NULL,
            reason TEXT,
            created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
            FOREIGN KEY (bucket_id) REFERENCES subscription_traffic_buckets(id)
        )
        """
    )
    await db.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sub_traffic_adjustments_bucket_day
        ON subscription_traffic_adjustments(bucket_id, day_utc)
        """
    )
    await db.commit()
