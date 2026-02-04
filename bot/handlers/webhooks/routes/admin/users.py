"""
Маршруты: список пользователей и карточка пользователя.
"""
import asyncio
import datetime
import json
import logging

import aiosqlite
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


def _format_payment(payment):
    payment_id = payment.get("payment_id") or payment.get("id", "N/A")
    status = payment.get("status", "unknown")
    created_at = payment.get("created_at", 0)
    amount = 0
    meta = payment.get("meta", {})
    if isinstance(meta, dict):
        amount = meta.get("price") or meta.get("amount", 0)
    elif isinstance(meta, str):
        try:
            amount = (json.loads(meta).get("price") or json.loads(meta).get("amount", 0)) or 0
        except Exception:
            amount = 0
    if isinstance(amount, str):
        try:
            amount = float(amount)
        except (ValueError, TypeError):
            amount = 0
    return {
        "id": payment_id,
        "amount": amount,
        "status": status,
        "created_at": created_at,
        "created_at_formatted": datetime.datetime.fromtimestamp(created_at).strftime("%d.%m.%Y %H:%M") if created_at else "N/A",
    }


def register_users_routes(bp):
    @bp.route("/api/admin/users", methods=["POST", "OPTIONS"])
    def api_admin_users():
        if request.method == "OPTIONS":
            return options_response()
        try:
            user_id = authenticate_request()
            if not user_id:
                return jsonify({"error": "Invalid authentication"}), 401
            if not check_admin_access(user_id):
                return jsonify({"error": "Access denied"}), 403

            data = request.get_json(silent=True) or {}
            search = (data.get("search") or "").strip()
            page = int(data.get("page", 1))
            limit = int(data.get("limit", 20))

            from .....db import DB_PATH
            from .....db.accounts_db import (
                get_remnawave_mapping,
                get_telegram_id_for_account,
                get_username_for_account,
            )

            async def get_users():
                async with aiosqlite.connect(DB_PATH) as db:
                    db.row_factory = aiosqlite.Row
                    search_pattern = f"%{search}%" if search else None
                    if search:
                        async with db.execute(
                            "SELECT COUNT(DISTINCT a.account_id) as count FROM accounts a LEFT JOIN identities i ON i.account_id = a.account_id LEFT JOIN account_remnawave ar ON ar.account_id = a.account_id WHERE CAST(a.account_id AS TEXT) LIKE ? OR i.provider_user_id LIKE ? OR ar.remnawave_short_uuid LIKE ?",
                            (search_pattern, search_pattern, search_pattern),
                        ) as cur:
                            total = (await cur.fetchone())["count"] or 0
                        async with db.execute(
                            "SELECT DISTINCT a.account_id, a.created_at, a.last_seen FROM accounts a LEFT JOIN identities i ON i.account_id = a.account_id LEFT JOIN account_remnawave ar ON ar.account_id = a.account_id WHERE CAST(a.account_id AS TEXT) LIKE ? OR i.provider_user_id LIKE ? OR ar.remnawave_short_uuid LIKE ? ORDER BY a.last_seen DESC LIMIT ? OFFSET ?",
                            (search_pattern, search_pattern, search_pattern, limit, (page - 1) * limit),
                        ) as cur:
                            rows = await cur.fetchall()
                    else:
                        async with db.execute("SELECT COUNT(*) as count FROM accounts") as cur:
                            total = (await cur.fetchone())["count"] or 0
                        async with db.execute(
                            "SELECT account_id, created_at, last_seen FROM accounts ORDER BY last_seen DESC LIMIT ? OFFSET ?",
                            (limit, (page - 1) * limit),
                        ) as cur:
                            rows = await cur.fetchall()
                    users = []
                    for row in rows:
                        account_id = row["account_id"]
                        telegram_id = await get_telegram_id_for_account(account_id)
                        username = await get_username_for_account(account_id)
                        remna = await get_remnawave_mapping(account_id)
                        short_uuid = remna.get("remnawave_short_uuid") if remna else None
                        users.append({
                            "id": account_id,
                            "user_id": str(account_id),
                            "account_id": account_id,
                            "remnawave_short_uuid": short_uuid,
                            "telegram_id": telegram_id,
                            "username": username,
                            "first_seen": row["created_at"],
                            "last_seen": row["last_seen"],
                            "subscriptions_count": 1 if short_uuid else 0,
                        })
                    return users, total

            users, total = _run_async(get_users())
            return (
                jsonify({
                    "success": True,
                    "users": users,
                    "total": total,
                    "page": page,
                    "limit": limit,
                    "pages": (total + limit - 1) // limit if limit > 0 else 0,
                }),
                200,
                {**CORS_HEADERS, "Content-Type": "application/json"},
            )
        except Exception as e:
            logger.error("Ошибка в /api/admin/users: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500

    @bp.route("/api/admin/user/<user_id_param>", methods=["POST", "OPTIONS"])
    def api_admin_user_info(user_id_param):
        if request.method == "OPTIONS":
            return options_response()
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({"error": "Access denied"}), 403

            from .....db import DB_PATH
            from .....db.accounts_db import (
                get_account_id_by_identity,
                get_remnawave_mapping,
                get_telegram_id_for_account,
                get_username_for_account,
            )
            from .....db.payments_db import get_payments_by_user
            from .....services.subscription_service import get_subscriptions_for_account

            account_id = None
            if user_id_param.isdigit():
                account_id = int(user_id_param)
            if account_id is None:
                account_id = _run_async(get_account_id_by_identity("telegram", user_id_param))
            if account_id is None:
                account_id = _run_async(get_account_id_by_identity("password", (user_id_param or "").strip().lower()))
            if account_id is None:
                return jsonify({"error": "User not found"}), 404

            remna = _run_async(get_remnawave_mapping(account_id))
            remnawave_short_uuid = remna.get("remnawave_short_uuid") if remna else None
            telegram_id = _run_async(get_telegram_id_for_account(account_id))
            username = _run_async(get_username_for_account(account_id))
            subscriptions = _run_async(get_subscriptions_for_account(account_id))
            payments = _run_async(get_payments_by_user(str(account_id), limit=10))

            async def get_account_timestamps():
                async with aiosqlite.connect(DB_PATH) as db:
                    db.row_factory = aiosqlite.Row
                    async with db.execute("SELECT created_at, last_seen FROM accounts WHERE account_id = ?", (account_id,)) as cur:
                        row = await cur.fetchone()
                    return (row["created_at"] if row else 0, row["last_seen"] if row else 0)

            created_at, last_seen = _run_async(get_account_timestamps())

            formatted_subs = []
            for sub in subscriptions:
                expires_at = sub.get("expires_at", 0)
                is_active = sub.get("status") == "active"
                formatted_subs.append({
                    "id": sub.get("id", 0),
                    "name": sub.get("name", "Подписка"),
                    "status": sub.get("status", "active"),
                    "is_active": is_active,
                    "period": sub.get("period", "month"),
                    "device_limit": sub.get("device_limit", 1),
                    "created_at": sub.get("created_at", created_at),
                    "created_at_formatted": datetime.datetime.fromtimestamp(sub.get("created_at", created_at)).strftime("%d.%m.%Y %H:%M"),
                    "expires_at": expires_at,
                    "expires_at_formatted": datetime.datetime.fromtimestamp(expires_at).strftime("%d.%m.%Y %H:%M") if expires_at else "—",
                    "price": sub.get("price", 0),
                    "token": sub.get("short_uuid") or sub.get("token", ""),
                })

            formatted_payments = [_format_payment(p) for p in payments]

            return (
                jsonify({
                    "success": True,
                    "user": {
                        "user_id": str(account_id),
                        "account_id": account_id,
                        "remnawave_short_uuid": remnawave_short_uuid,
                        "telegram_id": telegram_id,
                        "username": username,
                        "first_seen": created_at,
                        "first_seen_formatted": datetime.datetime.fromtimestamp(created_at).strftime("%d.%m.%Y %H:%M"),
                        "last_seen": last_seen,
                        "last_seen_formatted": datetime.datetime.fromtimestamp(last_seen).strftime("%d.%m.%Y %H:%M"),
                    },
                    "subscriptions": formatted_subs,
                    "payments": formatted_payments,
                }),
                200,
                {**CORS_HEADERS, "Content-Type": "application/json"},
            )
        except Exception as e:
            logger.error("Ошибка в /api/admin/user: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500
