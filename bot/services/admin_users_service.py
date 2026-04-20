"""Service layer for admin users routes."""

from __future__ import annotations

import datetime
import json
import logging
import time

import aiosqlite

from bot.app_context import get_ctx
from bot.db import DB_PATH
from bot.db.payments_db import get_payments_by_user
from bot.db.subscriptions_db import (
    get_all_subscriptions_by_user,
    get_subscription_servers,
    is_subscription_active,
    update_subscription_expiry,
)
from bot.db.users_db import delete_user_completely, resolve_user_by_query

logger = logging.getLogger(__name__)


async def get_users_list(search: str, page: int, limit: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        base = "SELECT * FROM users WHERE 1=1"
        params = []
        if search:
            base += " AND (user_id LIKE ? OR (telegram_id IS NOT NULL AND telegram_id LIKE ?) OR (username IS NOT NULL AND username LIKE ?))"
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern, search_pattern])
        count_query = f"SELECT COUNT(*) as count FROM ({base})"
        async with db.execute(count_query, params) as cur:
            row = await cur.fetchone()
            total = row["count"] if row else 0
        base += " ORDER BY last_seen DESC LIMIT ? OFFSET ?"
        params.extend([limit, (page - 1) * limit])
        async with db.execute(base, params) as cur:
            rows = await cur.fetchall()
            users = []
            for row in rows:
                async with db.execute(
                    "SELECT COUNT(*) as count FROM subscriptions s JOIN users u ON s.subscriber_id = u.id WHERE u.user_id = ?",
                    (row["user_id"],),
                ) as sub_cur:
                    sub_row = await sub_cur.fetchone()
                    sub_count = sub_row["count"] if sub_row else 0
                users.append(
                    {
                        "id": row["id"],
                        "user_id": row["user_id"],
                        "telegram_id": row["telegram_id"] if "telegram_id" in row.keys() else None,
                        "username": row["username"] if "username" in row.keys() else None,
                        "first_seen": row["first_seen"],
                        "last_seen": row["last_seen"],
                        "subscriptions_count": sub_count,
                    }
                )
            return users, total


def _parse_payment_amount(meta):
    amount = 0
    if isinstance(meta, dict):
        amount = meta.get("price") or meta.get("amount", 0)
    elif isinstance(meta, str):
        try:
            parsed = json.loads(meta)
            amount = parsed.get("price") or parsed.get("amount", 0)
        except Exception:
            amount = 0
    if isinstance(amount, str):
        try:
            amount = float(amount)
        except (ValueError, TypeError):
            amount = 0
    return amount


async def get_user_info_payload(user_id_param: str):
    user = await resolve_user_by_query(user_id_param)
    if not user:
        return None
    user_id_resolved = user["user_id"]
    subscriptions = await get_all_subscriptions_by_user(user_id_resolved, include_deleted=True)
    payments = await get_payments_by_user(user_id_resolved, limit=10)

    formatted_subs = []
    for sub in subscriptions:
        expires_at = sub["expires_at"]
        formatted_subs.append(
            {
                "id": sub["id"],
                "name": (sub.get("name") or "").strip() or f"Подписка {sub['id']}",
                "status": sub["status"],
                "is_active": is_subscription_active(sub),
                "period": sub["period"],
                "device_limit": sub["device_limit"],
                "created_at": sub["created_at"],
                "created_at_formatted": datetime.datetime.fromtimestamp(sub["created_at"]).strftime("%d.%m.%Y %H:%M"),
                "expires_at": expires_at,
                "expires_at_formatted": datetime.datetime.fromtimestamp(expires_at).strftime("%d.%m.%Y %H:%M"),
                "price": sub["price"],
                "token": sub["subscription_token"],
            }
        )

    formatted_payments = []
    for payment in payments:
        payment_id = payment.get("payment_id") or payment.get("id", "N/A")
        status = payment.get("status", "unknown")
        created_at = payment.get("created_at", 0)
        amount = _parse_payment_amount(payment.get("meta", {}))
        formatted_payments.append(
            {
                "id": payment_id,
                "amount": amount,
                "status": status,
                "created_at": created_at,
                "created_at_formatted": datetime.datetime.fromtimestamp(created_at).strftime("%d.%m.%Y %H:%M")
                if created_at
                else "N/A",
            }
        )

    return {
        "user": {
            "user_id": user["user_id"],
            "telegram_id": user.get("telegram_id"),
            "username": user.get("username"),
            "first_seen": user["first_seen"],
            "first_seen_formatted": datetime.datetime.fromtimestamp(user["first_seen"]).strftime("%d.%m.%Y %H:%M"),
            "last_seen": user["last_seen"],
            "last_seen_formatted": datetime.datetime.fromtimestamp(user["last_seen"]).strftime("%d.%m.%Y %H:%M"),
        },
        "subscriptions": formatted_subs,
        "payments": formatted_payments,
    }


async def create_subscription_for_user(
    user_id_param: str,
    period: str,
    device_limit: int,
    name: str | None,
    expires_at: int | None,
):
    user = await resolve_user_by_query(user_id_param)
    if not user:
        return None, {"error": "User not found"}, 404
    user_id_resolved = user["user_id"]
    ctx = get_ctx()
    subscription_manager = ctx.subscription_manager
    server_manager = ctx.server_manager
    if not subscription_manager:
        return None, {"error": "Subscription manager not available"}, 503
    if not server_manager:
        return None, {"error": "Server manager not available"}, 503

    if period not in ("month", "3month"):
        return None, {"error": "Invalid period. Must be \"month\" or \"3month\""}, 400

    if expires_at:
        expires_at_timestamp = int(expires_at)
    else:
        days = 90 if period == "3month" else 30
        expires_at_timestamp = int(time.time()) + days * 24 * 60 * 60

    sub_dict, token = await subscription_manager.create_subscription_for_user(
        user_id=user_id_resolved,
        period=period,
        device_limit=device_limit,
        price=0.0,
        name=name,
    )
    subscription_id = sub_dict["id"]

    if expires_at:
        await update_subscription_expiry(subscription_id, expires_at_timestamp)
        expires_at_final = expires_at_timestamp
        logger.info("Дата истечения обновлена на %s для подписки %s", expires_at_timestamp, subscription_id)
    else:
        expires_at_final = sub_dict["expires_at"]

    group_id = sub_dict.get("group_id")
    servers_for_group = server_manager.get_servers_by_group(group_id)
    all_configured_servers = [s["name"] for s in servers_for_group if s.get("x3") is not None]
    successful_servers = []
    failed_servers = []

    if all_configured_servers:
        unique_email = f"{user_id_resolved}_{subscription_id}"
        for server_name in all_configured_servers:
            try:
                await subscription_manager.attach_server_to_subscription(
                    subscription_id=subscription_id,
                    server_name=server_name,
                    client_email=unique_email,
                    client_id=None,
                )
            except Exception as attach_e:
                if "UNIQUE constraint" in str(attach_e) or "already exists" in str(attach_e).lower():
                    pass
                else:
                    logger.error("Ошибка привязки сервера %s: %s", server_name, attach_e)

        for server_name in all_configured_servers:
            try:
                client_exists, client_created = await subscription_manager.ensure_client_on_server(
                    subscription_id=subscription_id,
                    server_name=server_name,
                    client_email=unique_email,
                    user_id=user_id_resolved,
                    expires_at=expires_at_final,
                    token=token,
                    device_limit=device_limit,
                )
                if client_exists:
                    successful_servers.append({"server": server_name, "created": client_created})
                else:
                    failed_servers.append({"server": server_name, "error": "Failed to create client"})
            except Exception as e:
                failed_servers.append({"server": server_name, "error": str(e)})

    payload = {
        "subscription": {
            "id": subscription_id,
            "name": (sub_dict.get("name") or "").strip() or f"Подписка {subscription_id}",
            "status": sub_dict["status"],
            "period": period,
            "device_limit": device_limit,
            "expires_at": expires_at_final,
            "expires_at_formatted": datetime.datetime.fromtimestamp(expires_at_final).strftime("%d.%m.%Y %H:%M"),
            "token": token,
        },
        "successful_servers": successful_servers,
        "failed_servers": failed_servers,
    }
    return payload, None, None


async def delete_user_and_clients(user_id_param: str):
    user = await resolve_user_by_query(user_id_param)
    if not user:
        return None, {"error": "User not found"}, 404
    user_id = user["user_id"]
    all_subscriptions = await get_all_subscriptions_by_user(user_id, include_deleted=True)
    server_manager = get_ctx().server_manager

    deleted = []
    failed = []
    if server_manager and all_subscriptions:
        for sub in all_subscriptions:
            sub_id = sub["id"]
            servers = await get_subscription_servers(sub_id)
            for server_info in servers:
                server_name = server_info["server_name"]
                client_email = server_info["client_email"]
                try:
                    xui, _ = server_manager.get_server_by_name(server_name)
                    if xui:
                        deleted_ok = await xui.deleteClient(client_email, timeout=30)
                        if deleted_ok:
                            if server_name not in deleted:
                                deleted.append(server_name)
                        else:
                            if server_name not in failed:
                                failed.append(server_name)
                    else:
                        if server_name not in failed:
                            failed.append(server_name)
                except Exception:
                    if server_name not in failed:
                        failed.append(server_name)

    delete_stats = await delete_user_completely(user_id)
    return {"stats": delete_stats, "deleted_servers": deleted, "failed_servers": failed}, None, None
