"""
Quart Blueprint: POST /api/admin/subscription/<id>, .../update, .../sync, .../delete.
"""
import asyncio
import datetime
import logging

import aiosqlite
from quart import Blueprint, request, jsonify

from bot.web.routes.admin_common import CORS_HEADERS, _cors_headers, require_admin
from bot.db import DB_PATH
from bot.db.subscriptions_db import (
    get_subscription_by_id_only,
    get_subscription_servers,
    update_subscription_name,
    update_subscription_expiry,
    update_subscription_status,
    update_subscription_device_limit,
    remove_subscription_server,
)
from bot.db.notifications_db import clear_subscription_notifications
from bot.handlers.webhooks.webhook_auth import get_server_manager, get_subscription_manager
from bot.handlers.webhooks.payment_processors import get_globals

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint("admin_subscriptions", __name__)

    @bp.route("/api/admin/subscription/<int:sub_id>", methods=["POST", "OPTIONS"])
    async def api_admin_subscription_info(sub_id):
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            _, err = await require_admin(request)
            if err:
                return err
            await request.get_json(silent=True) or {}
            sub = await get_subscription_by_id_only(sub_id)
            if not sub:
                return jsonify({"error": "Subscription not found"}), 404, _cors_headers()
            servers = await get_subscription_servers(sub_id)
            return jsonify({
                "success": True,
                "subscription": {
                    "id": sub["id"],
                    "name": sub.get("name", f"Подписка {sub['id']}"),
                    "status": sub["status"],
                    "period": sub["period"],
                    "device_limit": sub["device_limit"],
                    "created_at": sub["created_at"],
                    "created_at_formatted": datetime.datetime.fromtimestamp(sub["created_at"]).strftime("%d.%m.%Y %H:%M"),
                    "expires_at": sub["expires_at"],
                    "expires_at_formatted": datetime.datetime.fromtimestamp(sub["expires_at"]).strftime("%d.%m.%Y %H:%M"),
                    "price": sub["price"],
                    "token": sub["subscription_token"],
                },
                "servers": servers,
            }), 200, _cors_headers()
        except Exception as e:
            logger.error("Ошибка в /api/admin/subscription: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500, _cors_headers()

    @bp.route("/api/admin/subscription/<int:sub_id>/update", methods=["POST", "OPTIONS"])
    async def api_admin_subscription_update(sub_id):
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            _, err = await require_admin(request)
            if err:
                return err
            data = await request.get_json(silent=True) or {}
            updates = {}
            if "name" in data:
                updates["name"] = data["name"]
            if "expires_at" in data:
                updates["expires_at"] = int(data["expires_at"])
            if "device_limit" in data:
                updates["device_limit"] = int(data["device_limit"])
            if "status" in data:
                updates["status"] = data["status"]
            if not updates:
                return jsonify({"error": "No fields to update"}), 400, _cors_headers()

            sub = await get_subscription_by_id_only(sub_id)
            if not sub:
                return jsonify({"error": "Subscription not found"}), 404, _cors_headers()
            old_status = sub["status"]
            old_expires_at = sub["expires_at"]
            old_device_limit = sub["device_limit"]

            if "status" in updates:
                new_status = updates["status"]
                if old_status in ("active", "expired") and new_status in ("active", "expired") and old_status != new_status:
                    return jsonify({
                        "error": "Нельзя вручную менять статус между \"active\" и \"expired\". Статус обновляется автоматически при изменении даты истечения (expires_at).",
                    }), 400, _cors_headers()
                if new_status != "deleted" and old_status == "deleted":
                    return jsonify({
                        "error": f"Нельзя изменить статус \"{old_status}\" на \"{new_status}\". Статус \"deleted\" является финальным.",
                    }), 400, _cors_headers()

            if "name" in updates:
                await update_subscription_name(sub_id, updates["name"])
            if "expires_at" in updates:
                await update_subscription_expiry(sub_id, updates["expires_at"])
            if "device_limit" in updates:
                await update_subscription_device_limit(sub_id, updates["device_limit"])
            if "status" in updates and updates["status"] == "deleted":
                await update_subscription_status(sub_id, updates["status"])
                await clear_subscription_notifications(sub_id)

            updated_sub = await get_subscription_by_id_only(sub_id)
            managers = get_globals()
            server_manager = managers.get("server_manager")
            subscription_manager = managers.get("subscription_manager")

            async def sync_with_servers():
                if not server_manager or not subscription_manager:
                    logger.warning("server_manager или subscription_manager не доступны для синхронизации")
                    return
                servers = await get_subscription_servers(sub_id)
                if not servers:
                    logger.info("Подписка %s не имеет привязанных серверов, синхронизация не требуется", sub_id)
                    return
                subscriber_id = updated_sub.get("subscriber_id")
                if not subscriber_id:
                    logger.warning("Подписка %s не имеет subscriber_id, синхронизация невозможна", sub_id)
                    return

                async def get_user_id_from_subscriber():
                    async with aiosqlite.connect(DB_PATH) as db:
                        db.row_factory = aiosqlite.Row
                        async with db.execute("SELECT user_id FROM users WHERE id = ?", (subscriber_id,)) as cur:
                            row = await cur.fetchone()
                            return row["user_id"] if row else None

                user_id = await get_user_id_from_subscriber()
                if not user_id:
                    logger.warning("Не найден user_id для subscriber_id=%s", subscriber_id)
                    return
                new_status = updated_sub["status"]
                new_expires_at = updated_sub["expires_at"]
                new_device_limit = updated_sub["device_limit"]
                token = updated_sub["subscription_token"]

                if new_status in ["expired", "deleted"] and old_status != new_status:
                    logger.info("Статус подписки %s изменился на %s, удаляем клиентов с серверов", sub_id, new_status)

                    async def delete_clients_with_timeout():
                        deleted_count = 0
                        failed_count = 0
                        for server_info in servers:
                            server_name = server_info["server_name"]
                            client_email = server_info["client_email"]
                            try:
                                xui, _ = server_manager.get_server_by_name(server_name)
                                if xui:
                                    try:
                                        await asyncio.wait_for(xui.deleteClient(client_email, 5), timeout=8.0)
                                        deleted_count += 1
                                    except asyncio.TimeoutError:
                                        failed_count += 1
                                    except Exception as delete_e:
                                        failed_count += 1
                                else:
                                    failed_count += 1
                            except Exception as e:
                                logger.error("Ошибка при удалении клиента %s с сервера %s: %s", client_email, server_name, e)
                                failed_count += 1
                        return deleted_count, failed_count

                    try:
                        deleted_count, failed_count = await asyncio.wait_for(delete_clients_with_timeout(), timeout=30.0)
                    except asyncio.TimeoutError:
                        logger.error("Таймаут при удалении клиентов для подписки %s", sub_id)
                        deleted_count = 0
                        failed_count = len(servers)
                    except Exception as e:
                        logger.error("Ошибка при удалении клиентов для подписки %s: %s", sub_id, e)
                        deleted_count = 0
                        failed_count = len(servers)

                    if deleted_count > 0 or failed_count < len(servers):
                        for server_info in servers:
                            server_name = server_info["server_name"]
                            try:
                                await remove_subscription_server(sub_id, server_name)
                            except Exception as e:
                                logger.error("Ошибка удаления связи подписки %s с сервером %s: %s", sub_id, server_name, e)

                elif new_status == "active" and old_status != "active" and old_status != "deleted":
                    logger.info("Статус подписки %s изменился на active, создаем/восстанавливаем клиентов", sub_id)
                    for server_info in servers:
                        server_name = server_info["server_name"]
                        client_email = server_info["client_email"]
                        try:
                            await subscription_manager.ensure_client_on_server(
                                subscription_id=sub_id,
                                server_name=server_name,
                                client_email=client_email,
                                user_id=user_id,
                                expires_at=new_expires_at,
                                token=token,
                                device_limit=new_device_limit,
                            )
                        except Exception as e:
                            logger.error("Ошибка создания/обновления клиента %s на сервере %s: %s", client_email, server_name, e)

                if ("expires_at" in updates or "device_limit" in updates) and new_status == "active":
                    if old_status == "active" or (old_status == "expired" and "expires_at" in updates):
                        for server_info in servers:
                            server_name = server_info["server_name"]
                            client_email = server_info["client_email"]
                            try:
                                xui, _ = server_manager.get_server_by_name(server_name)
                                if xui:
                                    server_config = server_manager.get_server_config(server_name)
                                    client_flow = (server_config.get("client_flow") or "").strip() or None if server_config else None
                                    if "expires_at" in updates:
                                        await xui.setClientExpiry(client_email, new_expires_at, flow=client_flow)
                                    if "device_limit" in updates:
                                        await xui.updateClientLimitIp(client_email, new_device_limit, flow=client_flow)
                            except Exception as e:
                                logger.error("Ошибка обновления клиента %s на сервере %s: %s", client_email, server_name, e)

            try:
                await asyncio.wait_for(sync_with_servers(), timeout=60.0)
            except asyncio.TimeoutError:
                logger.error("Таймаут при синхронизации подписки %s", sub_id)
            except Exception as sync_e:
                logger.error("Ошибка при синхронизации подписки %s: %s", sub_id, sync_e, exc_info=True)

            return jsonify({
                "success": True,
                "subscription": {
                    "id": updated_sub["id"],
                    "name": updated_sub.get("name", f"Подписка {updated_sub['id']}"),
                    "status": updated_sub["status"],
                    "period": updated_sub["period"],
                    "device_limit": updated_sub["device_limit"],
                    "created_at": updated_sub["created_at"],
                    "created_at_formatted": datetime.datetime.fromtimestamp(updated_sub["created_at"]).strftime("%d.%m.%Y %H:%M"),
                    "expires_at": updated_sub["expires_at"],
                    "expires_at_formatted": datetime.datetime.fromtimestamp(updated_sub["expires_at"]).strftime("%d.%m.%Y %H:%M"),
                    "price": updated_sub["price"],
                    "token": updated_sub["subscription_token"],
                },
            }), 200, _cors_headers()
        except Exception as e:
            logger.error("Ошибка в /api/admin/subscription/update: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500, _cors_headers()

    @bp.route("/api/admin/subscription/<int:sub_id>/sync", methods=["POST", "OPTIONS"])
    async def api_admin_subscription_sync(sub_id):
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            _, err = await require_admin(request)
            if err:
                return err
            await request.get_json(silent=True) or {}
            sub = await get_subscription_by_id_only(sub_id)
            if not sub:
                return jsonify({"error": "Subscription not found"}), 404, _cors_headers()
            servers = await get_subscription_servers(sub_id)
            subscription_manager = get_subscription_manager()
            if not subscription_manager:
                return jsonify({"error": "Subscription manager not available"}), 503, _cors_headers()

            async def get_user_id_from_sub():
                async with aiosqlite.connect(DB_PATH) as db:
                    db.row_factory = aiosqlite.Row
                    async with db.execute(
                        "SELECT u.user_id FROM users u JOIN subscriptions s ON u.id = s.subscriber_id WHERE s.id = ?",
                        (sub_id,),
                    ) as cur:
                        row = await cur.fetchone()
                        return row["user_id"] if row else ""

            user_id = await get_user_id_from_sub()

            async def sync_all_servers():
                sync_results = []
                for server_info in servers:
                    server_name = server_info["server_name"]
                    client_email = server_info["client_email"]
                    try:
                        await subscription_manager.ensure_client_on_server(
                            subscription_id=sub_id,
                            server_name=server_name,
                            client_email=client_email,
                            user_id=user_id,
                            expires_at=sub["expires_at"],
                            token=sub["subscription_token"],
                            device_limit=sub["device_limit"],
                        )
                        subscription_name = sub.get("name", sub["subscription_token"])
                        xui, _ = subscription_manager.server_manager.get_server_by_name(server_name)
                        if xui:
                            try:
                                client_info = await xui.get_client_info(client_email)
                                if client_info:
                                    current_sub_id = client_info["client"].get("subId", "")
                                    if current_sub_id != subscription_name:
                                        await xui.updateClientName(client_email, subscription_name)
                            except Exception as name_sync_e:
                                logger.warning("Ошибка синхронизации имени подписки на сервере %s: %s", server_name, name_sync_e)
                        sync_results.append({"server": server_name, "status": "success"})
                    except Exception as e:
                        logger.error("Ошибка синхронизации с сервером %s: %s", server_name, e)
                        sync_results.append({"server": server_name, "status": "error", "error": str(e)})
                return sync_results

            sync_results = await sync_all_servers()
            return jsonify({"success": True, "sync_results": sync_results}), 200, _cors_headers()
        except Exception as e:
            logger.error("Ошибка в /api/admin/subscription/sync: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500, _cors_headers()

    @bp.route("/api/admin/subscription/<int:sub_id>/delete", methods=["POST", "OPTIONS"])
    async def api_admin_subscription_delete(sub_id):
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            admin_id, err = await require_admin(request)
            if err:
                return err
            data = await request.get_json(silent=True) or {}
            if not data.get("confirm", False):
                return jsonify({"error": "Confirmation required"}), 400, _cors_headers()
            sub = await get_subscription_by_id_only(sub_id)
            if not sub:
                return jsonify({"error": "Subscription not found"}), 404, _cors_headers()
            servers = await get_subscription_servers(sub_id)
            server_manager = get_server_manager()

            async def delete_clients_from_servers():
                deleted = []
                failed = []
                if server_manager and servers:
                    for server_info in servers:
                        server_name = server_info["server_name"]
                        client_email = server_info["client_email"]
                        try:
                            xui, _ = server_manager.get_server_by_name(server_name)
                            if xui:
                                result = await xui.deleteClient(client_email, timeout=30)
                                if result is not None:
                                    status_code = getattr(result, "status_code", None)
                                    if status_code == 200:
                                        deleted.append(server_name)
                                    else:
                                        failed.append(server_name)
                                else:
                                    failed.append(server_name)
                            else:
                                failed.append(server_name)
                        except Exception as e:
                            failed.append(server_name)
                            logger.error("Ошибка удаления клиента %s с сервера %s: %s", client_email, server_name, e, exc_info=True)
                return deleted, failed

            deleted_servers, failed_servers = await delete_clients_from_servers()
            for server_info in servers:
                try:
                    await remove_subscription_server(sub_id, server_info["server_name"])
                except Exception as e:
                    logger.error("Ошибка удаления связи подписки %s с сервером %s: %s", sub_id, server_info["server_name"], e)

            async def delete_subscription():
                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
                    await db.commit()

            await delete_subscription()
            logger.info("Админ %s удалил подписку %s", admin_id, sub_id)
            return jsonify({
                "success": True,
                "message": "Подписка удалена",
                "deleted_servers": deleted_servers,
                "failed_servers": failed_servers,
            }), 200, _cors_headers()
        except Exception as e:
            logger.error("Ошибка в /api/admin/subscription/delete: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500, _cors_headers()

    return bp
