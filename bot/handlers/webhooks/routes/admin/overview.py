"""
Админ: сводные данные (количество пользователей, платежи).
Используется рассылкой для числа получателей; при необходимости — другими экранами админки.
"""
import json
import logging
import time

from flask import request

from ...webhook_utils import require_admin, APIResponse, run_async, AuthContext, handle_options

logger = logging.getLogger(__name__)


def register_overview_routes(bp):
    @bp.route("/api/admin/overview", methods=["POST", "OPTIONS"])
    @require_admin
    def api_admin_overview(auth: AuthContext):
        if request.method == "OPTIONS":
            return handle_options()
        try:
            async def fetch_overview():
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

                total_users, new_users_30d = await get_user_counts()
                total_payments, succeeded_payments, total_revenue = await get_payment_counts()

                return APIResponse.success(stats={
                    "users": {"total": total_users, "new_30d": new_users_30d},
                    "subscriptions": {"total": 0, "active": 0, "expired": 0, "deleted": 0, "trial": 0},
                    "payments": {
                        "total": total_payments,
                        "succeeded": succeeded_payments,
                        "revenue": round(total_revenue, 2),
                    },
                    "business": {"mrr": 0, "mrr_change": 0, "mrr_change_percent": 0},
                })

            return run_async(fetch_overview())
        except Exception as e:
            logger.error("Ошибка в /api/admin/overview: %s", e, exc_info=True)
            return APIResponse.internal_error()
