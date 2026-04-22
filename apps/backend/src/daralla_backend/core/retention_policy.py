"""Centralized retention policy settings."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int_env(name: str, default: int, *, min_value: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(min_value, value)


@dataclass(frozen=True)
class RetentionPolicy:
    payments_retention_days: int
    deleted_subscriptions_retention_days: int
    auto_delete_inactive_users_days: int
    notifications_sent_retention_days: int
    notification_metrics_retention_days: int
    server_load_retention_days: int
    events_raw_retention_days: int
    daily_agg_retention_days: int
    subscriptions_servers_on_delete: str
    dry_run: bool


def get_retention_policy() -> RetentionPolicy:
    mode = (os.getenv("SUBSCRIPTION_SERVERS_ON_DELETE", "immediate") or "immediate").strip().lower()
    if mode not in ("immediate", "deferred"):
        mode = "immediate"
    dry_run_raw = (os.getenv("RETENTION_DRY_RUN", "0") or "0").strip().lower()
    dry_run = dry_run_raw in ("1", "true", "yes", "on")
    return RetentionPolicy(
        payments_retention_days=_int_env("PAYMENTS_RETENTION_DAYS", 365),
        deleted_subscriptions_retention_days=_int_env("DELETED_SUBSCRIPTIONS_RETENTION_DAYS", 365),
        auto_delete_inactive_users_days=_int_env("AUTO_DELETE_INACTIVE_USERS_DAYS", 365),
        notifications_sent_retention_days=_int_env("NOTIFICATIONS_SENT_RETENTION_DAYS", 90),
        notification_metrics_retention_days=_int_env("NOTIFICATION_METRICS_RETENTION_DAYS", 730),
        server_load_retention_days=_int_env("SERVER_LOAD_RETENTION_DAYS", 30),
        events_raw_retention_days=_int_env("EVENTS_RAW_RETENTION_DAYS", 365),
        daily_agg_retention_days=_int_env("DAILY_AGG_RETENTION_DAYS", 730),
        subscriptions_servers_on_delete=mode,
        dry_run=dry_run,
    )
