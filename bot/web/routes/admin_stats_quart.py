"""
Quart Blueprint: POST /api/admin/stats (dashboard statistics).
"""
import json
import logging
import time

import aiosqlite
from quart import Blueprint, request, jsonify

from bot.web.routes.admin_common import CORS_HEADERS, _cors_headers, require_admin
from bot.db import DB_PATH
from bot.db.subscriptions_db import get_subscription_statistics

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


async def _get_payment_stats():
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
        async with db.execute(
            "SELECT meta FROM payments WHERE status = 'succeeded'"
        ) as cur:
            rows = await cur.fetchall()
            total_revenue = 0
            for row in rows:
                if row["meta"]:
                    try:
                        meta = (
                            json.loads(row["meta"])
                            if isinstance(row["meta"], str)
                            else row["meta"]
                        )
                        amount = meta.get("amount") or meta.get("price", 0)
                        if isinstance(amount, str):
                            try:
                                amount = float(amount)
                            except (ValueError, TypeError):
                                amount = 0
                        if isinstance(amount, (int, float)) and amount > 0:
                            total_revenue += amount
                    except Exception as e:
                        logger.debug("Ошибка парсинга meta платежа для дохода: %s", e)
            return total_payments, succeeded_payments, total_revenue


def create_blueprint(bot_app):
    bp = Blueprint("admin_stats", __name__)

    @bp.route("/api/admin/stats", methods=["POST", "OPTIONS"])
    async def api_admin_stats():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            _, err = await require_admin(request)
            if err:
                return err
            try:
                await request.get_json(silent=True) or {}
            except Exception as json_e:
                logger.warning("Ошибка парсинга JSON в /api/admin/stats: %s", json_e)

            stats = await get_subscription_statistics()
            total_users, new_users_30d = await _get_user_stats()
            total_payments, succeeded_payments, total_revenue = await _get_payment_stats()

            return jsonify({
                "success": True,
                "stats": {
                    "users": {"total": total_users, "new_30d": new_users_30d},
                    "subscriptions": {
                        "total": stats.get("total", stats.get("total_subscriptions", 0)),
                        "active": stats.get("active", stats.get("active_subscriptions", 0)),
                        "expired": stats.get("expired", stats.get("expired_subscriptions", 0)),
                        "deleted": stats.get("deleted", stats.get("deleted_subscriptions", 0)),
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
            }), 200, _cors_headers()
        except Exception as e:
            logger.error("Ошибка в /api/admin/stats: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500, _cors_headers()

    return bp
