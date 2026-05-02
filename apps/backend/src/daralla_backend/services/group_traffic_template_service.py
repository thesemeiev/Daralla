"""Материализация шаблона трафика группы серверов в per-subscription buckets."""

from __future__ import annotations

import logging

from daralla_backend.db.servers_db import (
    get_active_server_names_for_group,
    get_server_group_traffic_limited_servers,
    get_server_group_traffic_template,
)
from daralla_backend.db.subscriptions_db import (
    create_subscription_traffic_bucket,
    ensure_default_unlimited_bucket,
    get_subscription_by_id_only,
    list_subscription_traffic_buckets,
    set_subscription_server_bucket,
    update_subscription_traffic_bucket,
)
from daralla_backend.services.traffic_bucket_service import (
    get_traffic_bucket_service,
    traffic_buckets_enabled,
)

logger = logging.getLogger(__name__)


def group_limited_bucket_stable_name(group_id: int) -> str:
    return f"group:{int(group_id)}:limited"


async def async_has_non_template_traffic_customization(subscription_id: int, group_id: int) -> bool:
    allowed = {"unlimited", group_limited_bucket_stable_name(group_id)}
    buckets = await list_subscription_traffic_buckets(subscription_id)
    if len(buckets) > 2:
        return True
    for b in buckets:
        n = str(b.get("name") or "")
        if n not in allowed:
            return True
    if len(buckets) == 2:
        names = {str(b.get("name") or "") for b in buckets}
        if names != allowed:
            return True
    return False


async def apply_template_to_subscription(
    subscription_id: int,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> dict:
    """
    Применяет шаблон трафика группы к подписке.
    При force=False пропускает подписки с кастомными пакетами (не из шаблона).
    """
    if not traffic_buckets_enabled():
        return {"ok": True, "skipped": True, "reason": "traffic_buckets_disabled", "dry_run": dry_run}

    sub = await get_subscription_by_id_only(subscription_id)
    if not sub:
        return {"ok": False, "error": "subscription_not_found"}

    group_id = sub.get("group_id")
    if group_id is None:
        return {"ok": True, "skipped": True, "reason": "no_group_id", "dry_run": dry_run}

    gid = int(group_id)
    tmpl = await get_server_group_traffic_template(gid)
    if not tmpl or not int(tmpl.get("enabled") or 0):
        if not dry_run:
            await ensure_default_unlimited_bucket(subscription_id)
            tbs = get_traffic_bucket_service()
            await tbs.ensure_default_mapping(subscription_id)
        return {"ok": True, "skipped": True, "reason": "template_disabled", "dry_run": dry_run}

    limited_set = set(await get_server_group_traffic_limited_servers(gid))
    active_servers = await get_active_server_names_for_group(gid)
    active_set = set(active_servers)

    invalid = limited_set - active_set
    if invalid:
        return {
            "ok": False,
            "error": "template_limited_servers_not_in_group",
            "invalid_servers": sorted(invalid),
        }

    is_unlimited_pack = bool(int(tmpl.get("is_unlimited") or 0))
    limit_bytes = int(tmpl.get("limit_bytes") or 0)
    window_days = max(1, int(tmpl.get("window_days") or 30))
    credit_total = max(1, int(tmpl.get("credit_periods_total") or 1))

    if limited_set and not is_unlimited_pack and limit_bytes <= 0:
        return {"ok": False, "error": "limit_bytes_required_when_limited_servers_selected"}

    if not force:
        if await async_has_non_template_traffic_customization(subscription_id, gid):
            return {"ok": True, "skipped": True, "reason": "custom_traffic", "dry_run": dry_run}

    default_id = await ensure_default_unlimited_bucket(subscription_id)
    stable_name = group_limited_bucket_stable_name(gid)

    if not limited_set:
        if dry_run:
            return {
                "ok": True,
                "would_apply": True,
                "mode": "all_unlimited",
                "servers": len(active_servers),
                "dry_run": True,
            }
        for sn in active_servers:
            await set_subscription_server_bucket(subscription_id, sn, default_id)
        tbs = get_traffic_bucket_service()
        await tbs.enqueue_enforcement_if_needed(subscription_id)
        return {"ok": True, "applied": True, "mode": "all_unlimited", "servers": len(active_servers)}

    buckets = await list_subscription_traffic_buckets(subscription_id)
    limited_row = next((b for b in buckets if str(b.get("name") or "") == stable_name), None)
    limited_id: int
    if limited_row:
        limited_id = int(limited_row["id"])
        if not dry_run:
            await update_subscription_traffic_bucket(
                limited_id,
                {
                    "limit_bytes": max(0, limit_bytes),
                    "is_unlimited": is_unlimited_pack,
                    "window_days": window_days,
                    "credit_periods_total": credit_total,
                },
            )
    else:
        if dry_run:
            limited_id = -1
        else:
            limited_id = await create_subscription_traffic_bucket(
                subscription_id,
                stable_name,
                limit_bytes=max(0, limit_bytes),
                is_unlimited=is_unlimited_pack,
                window_days=window_days,
                credit_periods_total=credit_total,
            )

    if dry_run:
        mapped_limited = sum(1 for s in active_servers if s in limited_set)
        mapped_def = len(active_servers) - mapped_limited
        return {
            "ok": True,
            "would_apply": True,
            "mode": "split",
            "limited_bucket_id": limited_id,
            "default_bucket_id": default_id,
            "servers_limited": mapped_limited,
            "servers_unlimited": mapped_def,
            "dry_run": True,
        }

    for sn in active_servers:
        if sn in limited_set:
            await set_subscription_server_bucket(subscription_id, sn, limited_id)
        else:
            await set_subscription_server_bucket(subscription_id, sn, default_id)

    tbs = get_traffic_bucket_service()
    await tbs.enqueue_enforcement_if_needed(subscription_id)
    return {
        "ok": True,
        "applied": True,
        "mode": "split",
        "limited_bucket_id": limited_id,
        "default_bucket_id": default_id,
        "servers": len(active_servers),
    }


async def apply_group_traffic_template_bulk(
    group_id: int,
    *,
    subscription_ids: list[int] | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> dict:
    from daralla_backend.db.subscriptions_db import list_subscription_ids_for_group

    gid = int(group_id)
    tmpl = await get_server_group_traffic_template(gid)
    if tmpl and int(tmpl.get("enabled") or 0):
        limited = set(await get_server_group_traffic_limited_servers(gid))
        active = set(await get_active_server_names_for_group(gid))
        invalid = limited - active
        if invalid:
            return {
                "ok": False,
                "error": "template_limited_servers_not_in_group",
                "invalid_servers": sorted(invalid),
            }

    ids = [int(x) for x in subscription_ids] if subscription_ids else await list_subscription_ids_for_group(gid)
    applied = 0
    skipped = 0
    errors: list[dict] = []
    details: list[dict] = []

    for sid in ids:
        try:
            r = await apply_template_to_subscription(sid, force=force, dry_run=dry_run)
            if not r.get("ok"):
                errors.append({"subscription_id": sid, "error": r.get("error", "unknown")})
                continue
            if r.get("skipped"):
                skipped += 1
            elif r.get("applied") or r.get("would_apply"):
                applied += 1
            details.append({"subscription_id": sid, **{k: v for k, v in r.items() if k != "ok"}})
        except Exception as exc:
            logger.exception("apply_template subscription_id=%s", sid)
            errors.append({"subscription_id": sid, "error": str(exc)})

    return {
        "ok": True,
        "group_id": gid,
        "total": len(ids),
        "applied": applied,
        "skipped": skipped,
        "errors": errors,
        "details": details if dry_run else None,
    }
