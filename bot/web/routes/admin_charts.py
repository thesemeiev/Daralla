"""
Quart Blueprint: POST /api/admin/charts/* (user-growth, server-load, conversion, notifications, subscriptions).
"""
import logging

from quart import Blueprint, request, jsonify

from bot.web.routes.admin_common import _cors_headers, admin_route
from bot.db.users_db import get_user_growth_data
from bot.db.subscriptions_db import (
    get_conversion_data,
    get_subscription_types_statistics,
    get_subscription_dynamics_data,
    get_subscription_conversion_data,
)
from bot.db.notifications_db import get_notification_stats, get_daily_notification_stats
logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint("admin_charts", __name__)

    @bp.route("/api/admin/charts/user-growth", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_charts_user_growth(request, admin_id):
        data = await request.get_json(silent=True) or {}
        days = int(data.get("days", 30))
        growth_data = await get_user_growth_data(days)
        return jsonify({"success": True, "data": growth_data}), 200, _cors_headers()

    @bp.route("/api/admin/charts/server-load", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_charts_server_load(request, admin_id):
        _ = (request, admin_id)
        return jsonify({
            "success": True,
            "data": {"servers": [], "locations": []},
        }), 200, _cors_headers()

    @bp.route("/api/admin/charts/conversion", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_charts_conversion(request, admin_id):
        data = await request.get_json(silent=True) or {}
        days = int(data.get("days", 30))
        conversion_data = await get_conversion_data(days)
        return jsonify({"success": True, "data": conversion_data}), 200, _cors_headers()

    @bp.route("/api/admin/charts/notifications", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_charts_notifications(request, admin_id):
        data = await request.get_json(silent=True) or {}
        days = int(data.get("days", 7))
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
            chart_data["daily"].append({
                "date": date_str,
                "total": total,
                "success": success,
                "failed": failed,
                "success_rate": (success / total * 100) if total > 0 else 0,
            })
        chart_data["daily"].sort(key=lambda x: x["date"])
        return jsonify({"success": True, "data": chart_data}), 200, _cors_headers()

    @bp.route("/api/admin/charts/subscriptions", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_charts_subscriptions(request, admin_id):
        data = await request.get_json(silent=True) or {}
        days = int(data.get("days", 30))
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
        result = {
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
        return jsonify(result), 200, _cors_headers()

    return bp
