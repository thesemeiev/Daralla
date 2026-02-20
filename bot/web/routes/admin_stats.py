"""
Quart Blueprint: POST /api/admin/stats (dashboard statistics).
"""
import logging
import time

import aiosqlite
from quart import Blueprint, request, jsonify

from bot.web.routes.admin_common import _cors_headers, admin_route
from bot.db import DB_PATH
from bot.db.subscriptions_db import get_subscription_statistics
from bot.db.payments_db import get_revenue_by_gateway, get_daily_revenue

logger = logging.getLogger(__name__)


async def _get_user_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT COUNT(*) as count FROM users") as cur:
            row = await cur.fetchone()
            total_users = row["count"] if row else 0
        thirty_days_ago = int(time.time()) - (30 * 24 * 60 * 60)
        async with db.execute(
            "SELECT COUNT(*) as count FROM users WHERE first_seen >= ?",
            (thirty_days_ago,),
        ) as cur:
            row = await cur.fetchone()
            new_users_30d = row["count"] if row else 0
        return total_users, new_users_30d


def create_blueprint(bot_app):
    bp = Blueprint("admin_stats", __name__)

    @bp.route("/api/admin/stats", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_stats(request, admin_id):
        try:
            await request.get_json(silent=True) or {}
        except Exception as json_e:
            logger.warning("Ошибка парсинга JSON в /api/admin/stats: %s", json_e)

        stats = await get_subscription_statistics()
        total_users, new_users_30d = await _get_user_stats()
        daily_revenue = await get_daily_revenue(30)
        gateway_split = await get_revenue_by_gateway(30)

        active_subs = stats.get("active", stats.get("active_subscriptions", 0))
        users_with_subs = stats.get("users_with_active_subs", 0)
        conversion_rate = round(users_with_subs / total_users * 100, 1) if total_users > 0 else 0

        return jsonify({
            "success": True,
            "stats": {
                "users": {"total": total_users, "new_30d": new_users_30d},
                "subscriptions": {
                    "total": stats.get("total", stats.get("total_subscriptions", 0)),
                    "active": active_subs,
                    "expired": stats.get("expired", stats.get("expired_subscriptions", 0)),
                    "deleted": stats.get("deleted", stats.get("deleted_subscriptions", 0)),
                    "trial": stats.get("trial", 0),
                },
                "mrr": stats.get("mrr", 0),
                "mrr_change_percent": stats.get("mrr_change_percent", 0),
                "conversion_rate": conversion_rate,
                "daily_revenue": daily_revenue,
                "gateway_split": gateway_split,
            },
        }), 200, _cors_headers()

    return bp
