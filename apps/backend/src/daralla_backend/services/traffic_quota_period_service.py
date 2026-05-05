"""Периодная квота включённого трафика: календарный месяц (UTC), докупка отдельно."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from daralla_backend.db.servers_db import get_server_group_traffic_template
from daralla_backend.db.subscriptions_db import (
    get_subscription_by_id_only,
    get_subscription_traffic_bucket,
    get_subscription_traffic_quota,
    list_subscription_ids_for_calendar_quota_reset,
    list_subscription_traffic_buckets,
    upsert_subscription_traffic_quota_row,
)
from daralla_backend.services.group_traffic_bucket_names import group_limited_bucket_stable_name
from daralla_backend.services.traffic_bucket_service import traffic_buckets_enabled

logger = logging.getLogger(__name__)


def current_month_start_unix(now_ts: int | None = None) -> int:
    """Unix timestamp начала текущего календарного месяца в UTC."""
    ts = int(time.time()) if now_ts is None else int(now_ts)
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    start = datetime(dt.year, dt.month, 1, tzinfo=timezone.utc)
    return int(start.timestamp())


async def _resolve_group_limited_bucket_id(subscription_id: int, group_id: int) -> tuple[int | None, int]:
    """Возвращает (limited_bucket_id или None, monthly_limit_bytes из шаблона)."""
    tmpl = await get_server_group_traffic_template(int(group_id))
    if not tmpl or not int(tmpl.get("enabled") or 0):
        return None, 0
    if bool(int(tmpl.get("is_unlimited") or 0)):
        return None, 0
    limit_bytes = max(0, int(tmpl.get("limit_bytes") or 0))
    if limit_bytes <= 0:
        return None, 0

    stable = group_limited_bucket_stable_name(int(group_id))
    buckets = await list_subscription_traffic_buckets(int(subscription_id))
    limited_row = next((b for b in buckets if str(b.get("name") or "") == stable), None)
    if limited_row:
        return int(limited_row["id"]), limit_bytes
    lim_other = next((b for b in buckets if int(b.get("is_unlimited") or 0) == 0), None)
    if lim_other:
        return int(lim_other["id"]), limit_bytes
    return None, limit_bytes


async def _resolve_base_monthly_and_bucket_id(subscription_id: int) -> tuple[int | None, int]:
    """
    Базовый месячный лимит (байт) и актуальный limited_bucket_id для строки квоты.
    Сначала шаблон группы, иначе limit_bytes лимитного bucket из текущей строки квоты.
    """
    sid = int(subscription_id)
    sub = await get_subscription_by_id_only(sid)
    if not sub:
        return None, 0
    gid = sub.get("group_id")
    if gid is not None:
        bid, base = await _resolve_group_limited_bucket_id(sid, int(gid))
        if bid is not None and base > 0:
            return bid, base

    row = await get_subscription_traffic_quota(sid)
    if not row:
        return None, 0
    bid = int(row["limited_bucket_id"])
    bucket = await get_subscription_traffic_bucket(bid)
    if not bucket or int(bucket.get("subscription_id") or 0) != sid:
        return None, 0
    if bool(int(bucket.get("is_unlimited") or 0)):
        return None, 0
    base_monthly = max(0, int(bucket.get("limit_bytes") or 0))
    if base_monthly <= 0:
        return None, 0
    return bid, base_monthly


async def reset_included_quota_calendar(subscription_id: int, *, month_start_utc: int) -> bool:
    """
    Календарный сброс: allowance = base_monthly, used = 0, purchased без изменений,
    period_started_at = month_start_utc. Идемпотентно, если period_started_at >= month_start_utc.
    """
    if not traffic_buckets_enabled():
        return False
    sid = int(subscription_id)
    sub = await get_subscription_by_id_only(sid)
    if not sub or str(sub.get("status") or "") == "deleted":
        return False
    quota = await get_subscription_traffic_quota(sid)
    if not quota:
        return False
    ps = quota.get("period_started_at")
    if ps is not None and int(ps) >= int(month_start_utc):
        return False

    bid, base_monthly = await _resolve_base_monthly_and_bucket_id(sid)
    if bid is None or base_monthly <= 0:
        return False

    purchased = max(0, int(quota.get("purchased_remaining_bytes") or 0))

    await upsert_subscription_traffic_quota_row(
        sid,
        bid,
        included_allowance_bytes=base_monthly,
        included_used_bytes=0,
        purchased_remaining_bytes=purchased,
        bump_period_version=True,
        period_started_at=int(month_start_utc),
    )
    try:
        from daralla_backend.services.traffic_bucket_service import get_traffic_bucket_service

        await get_traffic_bucket_service().enqueue_enforcement_if_needed(sid)
    except Exception as enf_e:
        logger.warning("traffic_quota calendar_reset enqueue enforcement sub=%s: %s", sid, enf_e)
    logger.info(
        "traffic_quota calendar_reset sub=%s allowance=%s month_start=%s",
        sid,
        base_monthly,
        month_start_utc,
    )
    return True


async def run_calendar_reset_for_all(*, now_ts: int | None = None) -> dict:
    """Проход по всем квотам (кроме deleted): сброс тех, у кого period_started_at < начала текущего UTC-месяца."""
    if not traffic_buckets_enabled():
        return {"enabled": False, "month_start_utc": 0, "candidates": 0, "reset": 0, "skipped": 0, "errors": 0}
    month_start = current_month_start_unix(now_ts)
    ids = await list_subscription_ids_for_calendar_quota_reset()
    reset = 0
    skipped = 0
    errors = 0
    for sid in ids:
        try:
            if await reset_included_quota_calendar(sid, month_start_utc=month_start):
                reset += 1
            else:
                skipped += 1
        except Exception as exc:
            errors += 1
            logger.warning("traffic_quota calendar_reset failed sub=%s: %s", sid, exc)
    return {
        "enabled": True,
        "month_start_utc": month_start,
        "candidates": len(ids),
        "reset": reset,
        "skipped": skipped,
        "errors": errors,
    }


async def ensure_subscription_traffic_quota_for_new_template_subscription(
    subscription_id: int,
    *,
    limited_bucket_id: int,
    monthly_base_bytes: int,
) -> None:
    """После применения шаблона группы: создать строку квоты, если её ещё нет (месячный базовый пакет)."""
    if not traffic_buckets_enabled():
        return
    if monthly_base_bytes <= 0:
        return
    existing = await get_subscription_traffic_quota(int(subscription_id))
    if existing:
        return
    await upsert_subscription_traffic_quota_row(
        int(subscription_id),
        int(limited_bucket_id),
        included_allowance_bytes=int(monthly_base_bytes),
        included_used_bytes=0,
        purchased_remaining_bytes=0,
        bump_period_version=False,
    )
