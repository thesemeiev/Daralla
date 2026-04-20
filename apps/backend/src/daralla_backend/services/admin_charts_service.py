"""Service layer for admin charts routes."""

from __future__ import annotations

import asyncio
import logging
import time

from daralla_backend.app_context import get_ctx
from daralla_backend.db.notifications_db import get_daily_notification_stats, get_notification_stats
from daralla_backend.db.subscriptions_db import (
    get_conversion_data,
    get_subscription_conversion_data,
    get_subscription_dynamics_data,
    get_subscription_types_statistics,
)
from daralla_backend.db.users_db import get_user_growth_data


logger = logging.getLogger(__name__)
_SERVER_LOAD_CACHE_TTL_SECONDS = 5.0
_server_load_cache_lock = asyncio.Lock()
_server_load_cache = {"ts": 0.0, "payload": None}


def _server_info_map():
    server_manager = get_ctx().server_manager
    if not server_manager:
        return {}
    out = {}
    for server in server_manager.servers:
        server_name = server["name"]
        display_name = server["config"].get("display_name", server_name)
        location = server["config"].get("location") or "Other"
        out[server_name] = {"display_name": display_name, "location": location}
    return out


async def user_growth_payload(days: int):
    growth_data = await get_user_growth_data(days)
    return {"success": True, "data": growth_data}


async def server_load_payload():
    now = time.monotonic()
    cached = _server_load_cache.get("payload")
    if cached is not None and (now - _server_load_cache.get("ts", 0.0)) < _SERVER_LOAD_CACHE_TTL_SECONDS:
        return cached

    async with _server_load_cache_lock:
        now_locked = time.monotonic()
        cached = _server_load_cache.get("payload")
        if cached is not None and (now_locked - _server_load_cache.get("ts", 0.0)) < _SERVER_LOAD_CACHE_TTL_SECONDS:
            return cached

        sm = get_ctx().server_manager
        server_load_data = await sm.get_server_load_data() if sm else []
        if not server_load_data:
            payload = {"success": True, "data": {"servers": [], "locations": []}}
            _server_load_cache["ts"] = now_locked
            _server_load_cache["payload"] = payload
            return payload

        info_map = _server_info_map()
        enriched_data = []
        for item in server_load_data:
            server_name = item["server_name"]
            info = info_map.get(server_name, {})
            enriched_data.append(
                {
                    "server_name": server_name,
                    "display_name": info.get("display_name", server_name),
                    "location": info.get("location", "Unknown"),
                    "online_clients": item.get("online_clients", 0),
                    "total_active": item.get("total_active", 0),
                    "offline_clients": item.get("offline_clients", 0),
                    "avg_online_24h": item.get("avg_online_24h", 0),
                    "max_online_24h": item.get("max_online_24h", 0),
                    "min_online_24h": item.get("min_online_24h", 0),
                    "samples_24h": item.get("samples_24h", 0),
                    "load_percentage": item.get("load_percentage", 0),
                }
            )

        location_stats = {}
        for item in enriched_data:
            location = item["location"]
            if location not in location_stats:
                location_stats[location] = {"location": location, "total_online": 0, "total_active": 0, "servers": []}
            location_stats[location]["total_online"] += item["online_clients"]
            location_stats[location]["total_active"] += item["total_active"]
            location_stats[location]["servers"].append(
                {
                    "server_name": item["server_name"],
                    "display_name": item["display_name"],
                    "online_clients": item["online_clients"],
                    "total_active": item["total_active"],
                }
            )

        payload = {"success": True, "data": {"servers": enriched_data, "locations": list(location_stats.values())}}
        _server_load_cache["ts"] = now_locked
        _server_load_cache["payload"] = payload
        return payload


async def conversion_payload(days: int):
    conversion_data = await get_conversion_data(days)
    return {"success": True, "data": conversion_data}


async def notifications_payload(days: int):
    stats = await get_notification_stats(days)
    daily_stats = await get_daily_notification_stats(days)
    chart_data = {
        "stats": {
            "total_sent": stats.get("total_sent", 0),
            "success_count": stats.get("success_count", 0),
            "failed_count": stats.get("failed_count", 0),
            "blocked_users": stats.get("blocked_users", 0),
            "success_rate": stats.get("success_rate", 0),
            "by_type": stats.get("by_type", []),
        },
        "daily": [],
    }
    for day_stat in daily_stats:
        date_str = day_stat.get("date", "")
        total = day_stat.get("total", 0) or 0
        success = day_stat.get("success", 0) or 0
        failed = total - success
        chart_data["daily"].append(
            {
                "date": date_str,
                "total": total,
                "success": success,
                "failed": failed,
                "success_rate": (success / total * 100) if total > 0 else 0,
            }
        )
    chart_data["daily"].sort(key=lambda x: x["date"])
    return {"success": True, "data": chart_data}


async def subscriptions_payload(days: int):
    types_stats = await get_subscription_types_statistics()
    dynamics_data = await get_subscription_dynamics_data(days)
    conversion_data = await get_subscription_conversion_data(days)
    total_trial = types_stats.get("trial_active", 0)
    total_purchased = types_stats.get("purchased_active", 0)
    total_active = types_stats.get("total_active", 0)
    if total_trial > 0:
        conversion_rate = (total_purchased / total_trial) * 100
    else:
        conversion_rate = conversion_data.get("conversion_rate", 0.0)
    return {
        "success": True,
        "data": {
            "types": {
                "trial_active": types_stats.get("trial_active", 0),
                "purchased_active": types_stats.get("purchased_active", 0),
                "month_active": types_stats.get("month_active", 0),
                "3month_active": types_stats.get("3month_active", 0),
                "total_active": total_active,
                "conversion_rate": round(conversion_rate, 2),
            },
            "dynamics": dynamics_data,
            "conversion": conversion_data,
        },
    }
