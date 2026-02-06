"""
Маршруты: список пользователей и карточка пользователя.
"""
import datetime
import json
import logging

import aiosqlite
from flask import request

from ...webhook_utils import APIResponse, require_admin, handle_options, run_async, AuthContext

logger = logging.getLogger(__name__)


def _format_payment(payment):
    """Форматирует один платеж для вывода."""
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
    @require_admin
    def api_admin_users(auth: AuthContext):
        if request.method == "OPTIONS":
            return handle_options()

        data = request.get_json(silent=True) or {}
        search = (data.get("search") or "").strip()
        page = int(data.get("page", 1))
        limit = int(data.get("limit", 20))

        async def fetch():
            from .....db import DB_PATH
            from .....db.accounts_db import (
                get_remnawave_mapping,
                get_telegram_id_for_account,
                get_username_for_account,
            )

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
                        "account_id": account_id,
                        "remnawave_short_uuid": short_uuid,
                        "telegram_id": telegram_id,
                        "username": username,
                        "first_seen": row["created_at"],
                        "last_seen": row["last_seen"],
                        "subscriptions_count": 1 if short_uuid else 0,
                    })
                return users, total

        try:
            users, total = await fetch()
            return APIResponse.success(
                users=users,
                total=total,
                page=page,
                limit=limit,
                pages=(total + limit - 1) // limit if limit > 0 else 0,
            )
        except Exception as e:
            logger.error("Ошибка в /api/admin/users: %s", e, exc_info=True)
            return APIResponse.internal_error()

    @bp.route("/api/admin/user/<user_id_param>", methods=["POST", "OPTIONS"])
    @require_admin
    def api_admin_user_info(auth: AuthContext, user_id_param):
        if request.method == "OPTIONS":
            return handle_options()

        async def fetch():
            from .....db import DB_PATH
            from .....db.accounts_db import (
                get_account_id_by_identity,
                get_remnawave_mapping,
                get_telegram_id_for_account,
                get_username_for_account,
            )
            from .....db.payments_db import get_payments_by_account
            from .....services.subscription_service import get_subscriptions_for_account

            account_id = None
            if user_id_param.isdigit():
                account_id = int(user_id_param)
            if account_id is None:
                account_id = await get_account_id_by_identity("telegram", user_id_param)
            if account_id is None:
                account_id = await get_account_id_by_identity("password", (user_id_param or "").strip().lower())
            if account_id is None:
                return APIResponse.not_found('User not found')

            remna = await get_remnawave_mapping(account_id)
            remnawave_short_uuid = remna.get("remnawave_short_uuid") if remna else None
            telegram_id = await get_telegram_id_for_account(account_id)
            username = await get_username_for_account(account_id)
            subscriptions = await get_subscriptions_for_account(account_id)
            payments = await get_payments_by_account(account_id, limit=10)

            # Получить timestamps аккаунта
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT created_at, last_seen FROM accounts WHERE account_id = ?", (account_id,)) as cur:
                    row = await cur.fetchone()
                created_at = row["created_at"] if row else 0
                last_seen = row["last_seen"] if row else 0

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

            return APIResponse.success(
                user={
                    "account_id": account_id,
                    "remnawave_short_uuid": remnawave_short_uuid,
                    "telegram_id": telegram_id,
                    "username": username,
                    "first_seen": created_at,
                    "first_seen_formatted": datetime.datetime.fromtimestamp(created_at).strftime("%d.%m.%Y %H:%M"),
                    "last_seen": last_seen,
                    "last_seen_formatted": datetime.datetime.fromtimestamp(last_seen).strftime("%d.%m.%Y %H:%M"),
                },
                subscriptions=formatted_subs,
                payments=formatted_payments,
            )

        try:
            return run_async(fetch())
        except Exception as e:
            logger.error("Ошибка в /api/admin/user: %s", e, exc_info=True)
            return APIResponse.internal_error()

    @bp.route("/api/admin/user/<user_id_param>/delete", methods=["POST", "OPTIONS"])
    @require_admin
    def api_admin_user_delete(auth: AuthContext, user_id_param):
        if request.method == "OPTIONS":
            return handle_options()

        data = request.get_json(silent=True) or {}
        if not data.get("confirm"):
            return APIResponse.bad_request('Подтверждение требуется (confirm: true)')

        async def delete():
            from .....db.accounts_db import get_account_id_by_identity
            from .user_operations import delete_user_full

            account_id = None
            if user_id_param.isdigit():
                account_id = int(user_id_param)
            if account_id is None:
                account_id = await get_account_id_by_identity("telegram", user_id_param)
            if account_id is None:
                account_id = await get_account_id_by_identity("password", (user_id_param or "").strip().lower())
            if account_id is None:
                return APIResponse.not_found('User not found')

            subscriptions_deleted, payments_deleted = await delete_user_full(account_id)

            return APIResponse.success(
                stats={
                    "subscriptions_deleted": subscriptions_deleted,
                    "payments_deleted": payments_deleted,
                },
                deleted_servers=[],
            )

        try:
            return run_async(delete())
        except Exception as e:
            logger.error("Ошибка в /api/admin/user/delete: %s", e, exc_info=True)
            return APIResponse.internal_error()
