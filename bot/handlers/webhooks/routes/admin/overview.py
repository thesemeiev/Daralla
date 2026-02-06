"""
Админ: сводные данные (количество пользователей, платежи).
Используется рассылкой для числа получателей; при необходимости — другими экранами админки.
"""
import asyncio
import json
import logging
import time

from flask import request, jsonify

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


def register_overview_routes(bp):
    @bp.route("/api/admin/overview", methods=["POST", "OPTIONS"])
    def api_admin_overview():
        if request.method == "OPTIONS":
            return options_response()
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({"error": "Access denied"}), 403
            request.get_json(silent=True)

            from .....db import DB_PATH
            import aiosqlite

            async def get_user_counts():
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

            total_users, new_users_30d = _run_async(get_user_counts())

            async def get_payment_counts():
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

            total_payments, succeeded_payments, total_revenue = _run_async(get_payment_counts())

            return (
                jsonify({
                    "success": True,
                    "stats": {
                        "users": {"total": total_users, "new_30d": new_users_30d},
                        "subscriptions": {"total": 0, "active": 0, "expired": 0, "deleted": 0, "trial": 0},
                        "payments": {
                            "total": total_payments,
                            "succeeded": succeeded_payments,
                            "revenue": round(total_revenue, 2),
                        },
                        "business": {"mrr": 0, "mrr_change": 0, "mrr_change_percent": 0},
                    },
                }),
                200,
                {**CORS_HEADERS, "Content-Type": "application/json"},
            )
        except Exception as e:
            logger.error("Ошибка в /api/admin/overview: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500
