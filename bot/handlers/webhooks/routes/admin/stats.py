"""
Маршруты: статистика и графики (stats, server-load, notifications).
"""
import asyncio
import json
import logging
import time

from flask import request, jsonify

from ...context import get_app_context
from ...webhook_auth import authenticate_request, check_admin_access
from ._common import CORS_HEADERS, options_response

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def register_stats_routes(bp):
    @bp.route("/api/admin/stats", methods=["POST", "OPTIONS"])
    def api_admin_stats():
        if request.method == "OPTIONS":
            return options_response()
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({"error": "Access denied"}), 403
            try:
                data = request.get_json(silent=True) or {}
            except Exception as json_e:
                logger.warning("Ошибка парсинга JSON в /api/admin/stats: %s", json_e)
                data = {}

            from .....db import DB_PATH
            import aiosqlite

            stats = {
                "total": 0,
                "active": 0,
                "expired": 0,
                "deleted": 0,
                "trial": 0,
                "mrr": 0,
                "mrr_change": 0,
                "mrr_change_percent": 0,
            }

            async def get_user_stats():
                async with aiosqlite.connect(DB_PATH) as db:
                    db.row_factory = aiosqlite.Row
                    async with db.execute("SELECT COUNT(*) as count FROM accounts") as cur:
                        row = await cur.fetchone()
                        total_users = row["count"] if row else 0
                    thirty_days_ago = int(time.time()) - (30 * 24 * 60 * 60)
                    async with db.execute(
                        "SELECT COUNT(*) as count FROM accounts WHERE created_at >= ?",
                        (thirty_days_ago,),
                    ) as cur:
                        row = await cur.fetchone()
                        new_users_30d = row["count"] if row else 0
                    return total_users, new_users_30d

            total_users, new_users_30d = _run_async(get_user_stats())

            async def get_payment_stats():
                async with aiosqlite.connect(DB_PATH) as db:
                    db.row_factory = aiosqlite.Row
                    async with db.execute("SELECT COUNT(*) as count FROM payments") as cur:
                        row = await cur.fetchone()
                        total_payments = row["count"] if row else 0
                    async with db.execute(
                        "SELECT COUNT(*) as count FROM payments WHERE status = 'succeeded'"
                    ) as cur:
                        row = await cur.fetchone()
                        succeeded_payments = row["count"] if row else 0
                    async with db.execute("SELECT meta FROM payments WHERE status = 'succeeded'") as cur:
                        rows = await cur.fetchall()
                        total_revenue = 0
                        for row in rows:
                            if row["meta"]:
                                try:
                                    meta = json.loads(row["meta"]) if isinstance(row["meta"], str) else row["meta"]
                                    amount = meta.get("amount") or meta.get("price", 0)
                                    if isinstance(amount, str):
                                        try:
                                            amount = float(amount)
                                        except (ValueError, TypeError):
                                            amount = 0
                                    if isinstance(amount, (int, float)) and amount > 0:
                                        total_revenue += amount
                                except Exception as e:
                                    logger.debug("Ошибка парсинга meta платежа: %s", e)
                    return total_payments, succeeded_payments, total_revenue

            total_payments, succeeded_payments, total_revenue = _run_async(get_payment_stats())

            return (
                jsonify({
                    "success": True,
                    "stats": {
                        "users": {"total": total_users, "new_30d": new_users_30d},
                        "subscriptions": {
                            "total": stats.get("total", 0),
                            "active": stats.get("active", 0),
                            "expired": stats.get("expired", 0),
                            "deleted": stats.get("deleted", 0),
                            "trial": stats.get("trial", 0),
                        },
                        "payments": {
                            "total": total_payments,
                            "succeeded": succeeded_payments,
                            "revenue": round(total_revenue, 2),
                        },
                        "business": {
                            "mrr": stats.get("mrr", 0),
                            "mrr_change": stats.get("mrr_change", 0),
                            "mrr_change_percent": stats.get("mrr_change_percent", 0),
                        },
                    },
                }),
                200,
                {**CORS_HEADERS, "Content-Type": "application/json"},
            )
        except Exception as e:
            logger.error("Ошибка в /api/admin/stats: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500

    @bp.route("/api/admin/charts/server-load", methods=["POST", "OPTIONS"])
    def api_admin_charts_server_load():
        if request.method == "OPTIONS":
            return options_response()
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({"error": "Access denied"}), 403

            from .....db import get_server_load_data

            server_load_data = _run_async(get_server_load_data())
            if not server_load_data:
                return (
                    jsonify({"success": True, "data": {"servers": [], "locations": []}}),
                    200,
                    {**CORS_HEADERS, "Content-Type": "application/json"},
                )

            ctx = get_app_context()
            server_manager = ctx.server_manager if ctx else None
            server_info_map = {}
            if server_manager:
                for location, servers in server_manager.servers_by_location.items():
                    for server in servers:
                        server_name = server["name"]
                        server_info_map[server_name] = {
                            "display_name": server["config"].get("display_name", server_name),
                            "location": location,
                        }

            enriched_data = []
            for item in server_load_data:
                server_name = item["server_name"]
                info = server_info_map.get(server_name, {})
                enriched_data.append({
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
                })

            location_stats = {}
            for item in enriched_data:
                location = item["location"]
                if location not in location_stats:
                    location_stats[location] = {
                        "location": location,
                        "total_online": 0,
                        "total_active": 0,
                        "servers": [],
                    }
                location_stats[location]["total_online"] += item["online_clients"]
                location_stats[location]["total_active"] += item["total_active"]
                location_stats[location]["servers"].append({
                    "server_name": item["server_name"],
                    "display_name": item["display_name"],
                    "online_clients": item["online_clients"],
                    "total_active": item["total_active"],
                })

            return (
                jsonify({
                    "success": True,
                    "data": {
                        "servers": enriched_data,
                        "locations": list(location_stats.values()),
                    },
                }),
                200,
                {**CORS_HEADERS, "Content-Type": "application/json"},
            )
        except Exception as e:
            logger.error("Ошибка в /api/admin/charts/server-load: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500

    @bp.route("/api/admin/charts/notifications", methods=["POST", "OPTIONS"])
    def api_admin_charts_notifications():
        if request.method == "OPTIONS":
            return options_response()
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({"error": "Access denied"}), 403
            data = request.get_json(silent=True) or {}
            days = int(data.get("days", 7))

            from .....db.notifications_db import get_daily_notification_stats, get_notification_stats

            stats = _run_async(get_notification_stats(days))
            daily_stats = _run_async(get_daily_notification_stats(days))

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

            return (
                jsonify({"success": True, "data": chart_data}),
                200,
                {**CORS_HEADERS, "Content-Type": "application/json"},
            )
        except Exception as e:
            logger.error("Ошибка в /api/admin/charts/notifications: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500
