"""
Quart Blueprint: POST /api/admin/users, user/<id>, user/<id>/create-subscription, user/<id>/delete.
"""
import datetime
import json
import logging
import time

import aiosqlite
from quart import Blueprint, request, jsonify

from bot.web.routes.admin_common import CORS_HEADERS, _cors_headers, require_admin
from bot.db import DB_PATH
from bot.db.users_db import resolve_user_by_query
from bot.db.subscriptions_db import get_all_subscriptions_by_user, is_subscription_active
from bot.db.payments_db import get_payments_by_user
from bot.db.subscriptions_db import update_subscription_expiry
from bot.db.users_db import delete_user_completely
from bot.db.subscriptions_db import get_subscription_servers
from bot.handlers.webhooks.webhook_auth import get_server_manager, get_subscription_manager

logger = logging.getLogger(__name__)


async def _get_users_list(search, page, limit):
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
                users.append({
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "telegram_id": row["telegram_id"] if "telegram_id" in row.keys() else None,
                    "username": row["username"] if "username" in row.keys() else None,
                    "first_seen": row["first_seen"],
                    "last_seen": row["last_seen"],
                    "subscriptions_count": sub_count,
                })
            return users, total


def create_blueprint(bot_app):
    bp = Blueprint("admin_users", __name__)

    @bp.route("/api/admin/users", methods=["POST", "OPTIONS"])
    async def api_admin_users():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            _, err = await require_admin(request)
            if err:
                return err
            data = await request.get_json(silent=True) or {}
            search = data.get("search", "").strip()
            page = int(data.get("page", 1))
            limit = int(data.get("limit", 20))
            users, total = await _get_users_list(search, page, limit)
            return jsonify({
                "success": True,
                "users": users,
                "total": total,
                "page": page,
                "limit": limit,
                "pages": (total + limit - 1) // limit if limit > 0 else 0,
            }), 200, _cors_headers()
        except Exception as e:
            logger.error("Ошибка в /api/admin/users: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500, _cors_headers()

    @bp.route("/api/admin/user/<user_id_param>", methods=["POST", "OPTIONS"])
    async def api_admin_user_info(user_id_param):
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            _, err = await require_admin(request)
            if err:
                return err
            user = await resolve_user_by_query(user_id_param)
            if not user:
                return jsonify({"error": "User not found"}), 404, _cors_headers()
            user_id_resolved = user["user_id"]
            subscriptions = await get_all_subscriptions_by_user(user_id_resolved, include_deleted=True)
            payments = await get_payments_by_user(user_id_resolved, limit=10)
            formatted_subs = []
            for sub in subscriptions:
                expires_at = sub["expires_at"]
                formatted_subs.append({
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
                })
            formatted_payments = []
            for payment in payments:
                payment_id = payment.get("payment_id") or payment.get("id", "N/A")
                status = payment.get("status", "unknown")
                created_at = payment.get("created_at", 0)
                amount = 0
                meta = payment.get("meta", {})
                if isinstance(meta, dict):
                    amount = meta.get("price") or meta.get("amount", 0)
                elif isinstance(meta, str):
                    try:
                        amount = json.loads(meta).get("price") or json.loads(meta).get("amount", 0)
                    except Exception:
                        amount = 0
                if isinstance(amount, str):
                    try:
                        amount = float(amount)
                    except (ValueError, TypeError):
                        amount = 0
                formatted_payments.append({
                    "id": payment_id,
                    "amount": amount,
                    "status": status,
                    "created_at": created_at,
                    "created_at_formatted": datetime.datetime.fromtimestamp(created_at).strftime("%d.%m.%Y %H:%M") if created_at else "N/A",
                })
            return jsonify({
                "success": True,
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
            }), 200, _cors_headers()
        except Exception as e:
            logger.error("Ошибка в /api/admin/user: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500, _cors_headers()

    @bp.route("/api/admin/user/<user_id_param>/create-subscription", methods=["POST", "OPTIONS"])
    async def api_admin_user_create_subscription(user_id_param):
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            _, err = await require_admin(request)
            if err:
                return err
            data = await request.get_json(silent=True) or {}
            period = data.get("period", "month")
            device_limit = int(data.get("device_limit", 1))
            name = data.get("name") or None
            expires_at = data.get("expires_at")
            if period not in ("month", "3month"):
                return jsonify({"error": "Invalid period. Must be \"month\" or \"3month\""}), 400, _cors_headers()
            subscription_manager = get_subscription_manager()
            server_manager = get_server_manager()
            if not subscription_manager:
                return jsonify({"error": "Subscription manager not available"}), 503, _cors_headers()
            if not server_manager:
                return jsonify({"error": "Server manager not available"}), 503, _cors_headers()
            if expires_at:
                expires_at_timestamp = int(expires_at)
            else:
                days = 90 if period == "3month" else 30
                expires_at_timestamp = int(time.time()) + days * 24 * 60 * 60
            price = 0.0
            sub_dict, token = await subscription_manager.create_subscription_for_user(
                user_id=user_id_param,
                period=period,
                device_limit=device_limit,
                price=price,
                name=name,
            )
            subscription_id = sub_dict["id"]
            if expires_at:
                await update_subscription_expiry(subscription_id, expires_at_timestamp)
                expires_at_final = expires_at_timestamp
                logger.info("Дата истечения обновлена на %s для подписки %s", expires_at_timestamp, subscription_id)
            else:
                expires_at_final = sub_dict["expires_at"]
            logger.info("Подписка создана в БД: subscription_id=%s, user_id=%s, period=%s", subscription_id, user_id_param, period)
            group_id = sub_dict.get("group_id")
            servers_for_group = server_manager.get_servers_by_group(group_id)
            all_configured_servers = [s["name"] for s in servers_for_group if s.get("x3") is not None]
            successful_servers = []
            failed_servers = []

            if all_configured_servers:
                unique_email = f"{user_id_param}_{subscription_id}"
                logger.info("Создание клиентов на %s серверах для подписки %s", len(all_configured_servers), subscription_id)

                async def attach_servers_and_create_clients():
                    for server_name in all_configured_servers:
                        try:
                            await subscription_manager.attach_server_to_subscription(
                                subscription_id=subscription_id,
                                server_name=server_name,
                                client_email=unique_email,
                                client_id=None,
                            )
                            logger.info("Сервер %s привязан к подписке %s", server_name, subscription_id)
                        except Exception as attach_e:
                            if "UNIQUE constraint" in str(attach_e) or "already exists" in str(attach_e).lower():
                                logger.info("Сервер %s уже привязан к подписке %s", server_name, subscription_id)
                            else:
                                logger.error("Ошибка привязки сервера %s: %s", server_name, attach_e)
                    for server_name in all_configured_servers:
                        try:
                            client_exists, client_created = await subscription_manager.ensure_client_on_server(
                                subscription_id=subscription_id,
                                server_name=server_name,
                                client_email=unique_email,
                                user_id=user_id_param,
                                expires_at=expires_at_final,
                                token=token,
                                device_limit=device_limit,
                            )
                            if client_exists:
                                successful_servers.append({"server": server_name, "created": client_created})
                                if client_created:
                                    logger.info("Клиент создан на сервере %s", server_name)
                                else:
                                    logger.info("Клиент уже существует на сервере %s", server_name)
                            else:
                                failed_servers.append({"server": server_name, "error": "Failed to create client"})
                                logger.warning("Не удалось создать клиента на сервере %s", server_name)
                        except Exception as e:
                            failed_servers.append({"server": server_name, "error": str(e)})
                            logger.error("Ошибка создания клиента на сервере %s: %s", server_name, e)

                await attach_servers_and_create_clients()

            return jsonify({
                "success": True,
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
            }), 200, _cors_headers()
        except Exception as e:
            logger.error("Ошибка в /api/admin/user/create-subscription: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error", "details": str(e)}), 500, _cors_headers()

    @bp.route("/api/admin/user/<user_id>/delete", methods=["POST", "OPTIONS"])
    async def api_admin_user_delete(user_id):
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            admin_id, err = await require_admin(request)
            if err:
                return err
            data = await request.get_json(silent=True) or {}
            confirm = data.get("confirm", False)
            if not confirm:
                return jsonify({"error": "Confirmation required"}), 400, _cors_headers()
            all_subscriptions = await get_all_subscriptions_by_user(user_id, include_deleted=True)
            server_manager = get_server_manager()

            async def delete_all_clients_from_servers():
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
                                        logger.info(
                                            "Удален клиент %s с сервера %s при удалении пользователя %s",
                                            client_email,
                                            server_name,
                                            user_id,
                                        )
                                    else:
                                        if server_name not in failed:
                                            failed.append(server_name)
                                else:
                                    if server_name not in failed:
                                        failed.append(server_name)
                            except Exception as e:
                                if server_name not in failed:
                                    failed.append(server_name)
                                logger.error("Ошибка удаления клиента %s с сервера %s: %s", client_email, server_name, e, exc_info=True)
                return deleted, failed

            deleted_servers, failed_servers = await delete_all_clients_from_servers()
            delete_stats = await delete_user_completely(user_id)
            logger.info("Админ %s удалил пользователя %s", admin_id, user_id)
            return jsonify({
                "success": True,
                "stats": delete_stats,
                "deleted_servers": deleted_servers,
                "failed_servers": failed_servers,
            }), 200, _cors_headers()
        except Exception as e:
            logger.error("Ошибка в /api/admin/user/%s/delete: %s", user_id, e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500, _cors_headers()

    return bp
