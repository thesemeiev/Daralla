"""Subscription-related handlers extracted from api_user routes."""

import datetime
import time

from quart import jsonify, request

from bot.services.user_subscriptions_service import (
    is_active_subscription,
    list_user_subscriptions,
    rename_subscription_for_user,
    user_server_usage_map,
)
from bot.web.routes.admin_common import _cors_headers
from bot.web.routes.api_user_common import options_response_or_none, require_user_id
from bot.web.routes.api_user_helpers import normalize_map_lat_lng


async def handle_api_subscriptions(_auth, logger):
    opt = options_response_or_none()
    if opt:
        return opt
    try:
        user_id, err = await require_user_id(_auth)
        if err:
            return jsonify(err[0]), err[1]
        subscriptions = await list_user_subscriptions(user_id)
        current_time = int(time.time())
        formatted_subs = []
        for sub in subscriptions:
            expires_at = sub["expires_at"]
            is_active = is_active_subscription(sub)
            is_expired = expires_at < current_time
            expiry_datetime = datetime.datetime.fromtimestamp(expires_at)
            created_datetime = datetime.datetime.fromtimestamp(sub["created_at"])
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
                }
            )
        formatted_subs.sort(key=lambda x: (x["status"] != "active", -x["created_at"]))
        resp = jsonify(
            {
                "success": True,
                "subscriptions": formatted_subs,
                "total": len(formatted_subs),
                "active": len([s for s in formatted_subs if s["status"] == "active"]),
            }
        )
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        return resp, 200, _cors_headers()
    except Exception as e:
        logger.error("Ошибка в API /api/subscriptions: %s", e, exc_info=True)
        return jsonify({"error": "Internal server error"}), 500, _cors_headers()


async def handle_api_user_subscription_rename(_auth, sub_id, logger):
    opt = options_response_or_none()
    if opt:
        return opt
    try:
        user_id, err = await require_user_id(_auth)
        if err:
            return jsonify(err[0]), err[1]
        data = await request.get_json(silent=True) or {}
        new_name = (data.get("name") or "").strip()
        if not new_name:
            return jsonify({"error": "Name is required"}), 400
        renamed = await rename_subscription_for_user(sub_id, user_id, new_name)
        if not renamed:
            return jsonify({"error": "Subscription not found or access denied"}), 404
        return (
            jsonify(
                {
                    "success": True,
                    "message": "Subscription renamed successfully",
                    "name": new_name,
                }
            ),
            200,
            _cors_headers(),
        )
    except Exception as e:
        logger.error("Ошибка в API /api/user/subscription/%s/rename: %s", sub_id, e, exc_info=True)
        return jsonify({"error": "Internal server error"}), 500, _cors_headers()


async def handle_api_user_server_usage(_auth, logger):
    opt = options_response_or_none()
    if opt:
        return opt
    try:
        user_id, err = await require_user_id(_auth)
        if err:
            return jsonify(err[0]), err[1]
        from bot.app_context import get_ctx

        server_usage = await user_server_usage_map(user_id)
        server_manager = get_ctx().server_manager
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
        return jsonify({"success": True, "servers": servers_info}), 200, _cors_headers()
    except Exception as e:
        logger.error("Ошибка в API /api/user/server-usage: %s", e, exc_info=True)
        return jsonify({"error": "Internal server error"}), 500, _cors_headers()
