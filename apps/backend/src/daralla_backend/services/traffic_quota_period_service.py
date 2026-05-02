"""Периодная квота включённого трафика и сброс при оплате."""

from __future__ import annotations

import logging

from daralla_backend.db.servers_db import get_server_group_traffic_template
from daralla_backend.db.subscriptions_db import (
    get_subscription_by_id_only,
    get_subscription_traffic_quota,
    list_subscription_traffic_buckets,
    upsert_subscription_traffic_quota_row,
)
from daralla_backend.services.group_traffic_bucket_names import group_limited_bucket_stable_name
from daralla_backend.services.traffic_bucket_service import traffic_buckets_enabled

logger = logging.getLogger(__name__)


def tariff_month_multiplier_for_period(period_key: str | None, *, payment_days: int | None = None) -> int:
    """
    Множатель месяцев для включённой квоты: тариф с days=90 → 3, days=30 → 1.
    Неизвестный период — по payment_days или 1.
    """
    from daralla_backend.prices_config import get_tariff

    pk = str(period_key or "").strip().lower()
    tariff = get_tariff(pk)
    if tariff:
        try:
            d = max(1, int(tariff.get("days") or 30))
            return max(1, round(d / 30))
        except (TypeError, ValueError):
            return 1
    if payment_days and int(payment_days) > 0:
        return max(1, round(int(payment_days) / 30))
    return 1


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


async def reset_included_quota_after_payment(
    subscription_id: int,
    *,
    paid_period_key: str | None,
    payment_days: int | None = None,
) -> None:
    """После успешной оплаты/продления: новый allowance = base × множитель, included_used = 0; purchased не трогаем."""
    if not traffic_buckets_enabled():
        return
    sub = await get_subscription_by_id_only(int(subscription_id))
    if not sub:
        return
    gid = sub.get("group_id")
    if gid is None:
        return

    bid, base_monthly = await _resolve_group_limited_bucket_id(int(subscription_id), int(gid))
    if bid is None or base_monthly <= 0:
        return

    mult = tariff_month_multiplier_for_period(paid_period_key, payment_days=payment_days)
    allowance = base_monthly * mult

    existing = await get_subscription_traffic_quota(int(subscription_id))
    purchased = int(existing["purchased_remaining_bytes"]) if existing else 0

    await upsert_subscription_traffic_quota_row(
        int(subscription_id),
        bid,
        included_allowance_bytes=allowance,
        included_used_bytes=0,
        purchased_remaining_bytes=purchased,
        bump_period_version=True,
    )
    logger.info(
        "traffic_quota reset_after_payment sub=%s allowance=%s mult=%s period=%s",
        subscription_id,
        allowance,
        mult,
        paid_period_key,
    )


async def ensure_subscription_traffic_quota_for_new_template_subscription(
    subscription_id: int,
    *,
    limited_bucket_id: int,
    monthly_base_bytes: int,
) -> None:
    """После применения шаблона группы: создать строку квоты, если её ещё нет (один месячный эквивалент до первой оплаты)."""
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
