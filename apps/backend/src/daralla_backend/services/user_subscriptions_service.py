"""Service wrappers for user subscription operations used by HTTP routes."""

from __future__ import annotations

import datetime
import time

from daralla_backend.db.subscriptions_db import (
    get_all_subscriptions_by_user,
    get_subscription_by_id,
    get_subscription_traffic_quota,
    is_subscription_active,
    subscription_should_show_user_traffic_quota,
    update_subscription_name,
)
from daralla_backend.db.users_db import get_user_server_usage
from daralla_backend.prices_config import get_public_traffic_topup_packages, refresh_prices_from_db
from daralla_backend.services.sync_outbox_service import enqueue_subscription_sync_jobs, outbox_write_enabled
from daralla_backend.services.traffic_bucket_service import traffic_buckets_enabled


async def list_user_subscriptions(user_id: str):
    return await get_all_subscriptions_by_user(user_id)


def is_active_subscription(subscription: dict) -> bool:
    return is_subscription_active(subscription)


async def rename_subscription_for_user(sub_id: int, user_id: str, new_name: str) -> bool:
    sub = await get_subscription_by_id(sub_id, user_id)
    if not sub:
        return False
    await update_subscription_name(sub_id, new_name)
    if outbox_write_enabled():
        try:
            await enqueue_subscription_sync_jobs(int(sub_id), reason="user_rename_subscription")
        except Exception:
            # Ошибка outbox не должна ломать пользовательский rename.
            pass
    return True


async def user_server_usage_map(user_id: str):
    return await get_user_server_usage(user_id)


async def subscriptions_overview_payload(user_id: str, now_ts: int | None = None) -> dict:
    current_time = int(now_ts or time.time())
    await refresh_prices_from_db()
    traffic_topup_catalog: list[dict] = []
    if traffic_buckets_enabled():
        traffic_topup_catalog = get_public_traffic_topup_packages()
    subscriptions = await list_user_subscriptions(user_id)
    formatted_subs = []
    for sub in subscriptions:
        expires_at = sub["expires_at"]
        is_active = is_active_subscription(sub)
        is_expired = expires_at < current_time
        expiry_datetime = datetime.datetime.fromtimestamp(expires_at)
        created_datetime = datetime.datetime.fromtimestamp(sub["created_at"])
        traffic_quota = None
        if traffic_buckets_enabled():
            qrow = await get_subscription_traffic_quota(int(sub["id"]))
            if qrow and await subscription_should_show_user_traffic_quota(int(sub["id"]), dict(qrow)):
                traffic_quota = {
                    "included_allowance_bytes": int(qrow["included_allowance_bytes"]),
                    "included_used_bytes": int(qrow["included_used_bytes"]),
                    "purchased_remaining_bytes": int(qrow["purchased_remaining_bytes"]),
                    "traffic_period_version": int(qrow.get("traffic_period_version") or 0),
                }
        formatted_subs.append(
            {
                "id": sub["id"],
                "name": (sub.get("name") or "").strip() or f"Подписка {sub['id']}",
                "status": "active" if is_active else ("expired" if is_expired else sub["status"]),
                "period": sub["period"],
                "device_limit": sub["device_limit"],
                "created_at": sub["created_at"],
                "created_at_formatted": created_datetime.strftime("%d.%m.%Y %H:%M"),
                "expires_at": expires_at,
                "expires_at_formatted": expiry_datetime.strftime("%d.%m.%Y %H:%M"),
                "price": sub["price"],
                "token": sub["subscription_token"],
                "days_remaining": max(0, (expires_at - current_time) // (24 * 60 * 60))
                if is_active
                else 0,
                "traffic_quota": traffic_quota,
            }
        )
    formatted_subs.sort(key=lambda x: (x["status"] != "active", -x["created_at"]))
    traffic_topup_catalog: list[dict] = []
    if traffic_buckets_enabled() and any(s.get("traffic_quota") is not None for s in formatted_subs):
        traffic_topup_catalog = get_public_traffic_topup_packages()
    return {
        "success": True,
        "subscriptions": formatted_subs,
        "total": len(formatted_subs),
        "active": len([s for s in formatted_subs if s["status"] == "active"]),
        "traffic_topup_packages": traffic_topup_catalog,
    }


async def server_usage_payload(user_id: str, server_manager, normalize_map_lat_lng):
    server_usage = await user_server_usage_map(user_id)
    servers_info = []
    if server_manager:
        health_status = server_manager.get_server_health_status()
        for server in server_manager.servers:
            server_name = server["name"]
            display_name = server["config"].get("display_name", server_name)
            map_label = server["config"].get("map_label")
            location = server["config"].get("location") or "Other"
            raw_lat = server["config"].get("lat")
            raw_lng = server["config"].get("lng")
            lat, lng = normalize_map_lat_lng(raw_lat, raw_lng)
            usage_data = server_usage.get(server_name, {"count": 0, "percentage": 0})
            status_info = health_status.get(server_name, {})
            status = status_info.get("status", "unknown")
            servers_info.append(
                {
                    "name": server_name,
                    "display_name": display_name,
                    "map_label": map_label,
                    "location": location,
                    "lat": lat,
                    "lng": lng,
                    "usage_count": usage_data["count"],
                    "usage_percentage": usage_data["percentage"],
                    "status": status,
                }
            )
    return {"success": True, "servers": servers_info}
