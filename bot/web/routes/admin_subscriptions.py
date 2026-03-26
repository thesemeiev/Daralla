"""
Quart Blueprint: subscription-level admin actions (RemnaWave-only).
"""
import datetime
import logging

from quart import Blueprint, request, jsonify

from bot.web.routes.admin_common import _cors_headers, admin_route
from bot.db.subscriptions_db import (
    get_subscription_by_id_only,
    update_subscription_name,
    update_subscription_expiry,
    update_subscription_status,
    update_subscription_device_limit,
    get_subscriptions_page,
)
from bot.db.notifications_db import clear_subscription_notifications
from bot.app_context import get_ctx

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint("admin_subscriptions", __name__)

    @bp.route("/api/admin/subscriptions", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_subscriptions(request, admin_id):
        data = await request.get_json(silent=True) or {}
        page = int(data.get("page", 1) or 1)
        limit = int(data.get("limit", 20) or 20)
        status = (data.get("status") or "").strip() or None
        owner_query = (data.get("owner_query") or "").strip() or None
        long_only = bool(data.get("long_only", False))

        result = await get_subscriptions_page(
            page=page,
            limit=limit,
            status=status,
            owner_query=owner_query,
            long_only=long_only,
        )
        items = result.get("items") or []
        subscriptions = []
        for sub in items:
            created_at = sub.get("created_at") or 0
            expires_at = sub.get("expires_at") or 0
            subscriptions.append({
                "id": sub.get("id"),
                "name": (sub.get("name") or "").strip() or f"Подписка {sub.get('id')}",
                "status": sub.get("status"),
                "period": sub.get("period"),
                "device_limit": sub.get("device_limit"),
                "created_at": created_at,
                "created_at_formatted": datetime.datetime.fromtimestamp(created_at).strftime("%d.%m.%Y %H:%M") if created_at else "",
                "expires_at": expires_at,
                "expires_at_formatted": datetime.datetime.fromtimestamp(expires_at).strftime("%d.%m.%Y %H:%M") if expires_at else "",
                "price": sub.get("price"),
                "token": sub.get("subscription_token"),
                "user_id": sub.get("user_id"),
                "username": sub.get("username"),
            })

        total = result.get("total", 0)
        return jsonify({
            "success": True,
            "subscriptions": subscriptions,
            "total": total,
            "page": result.get("page", page),
            "limit": result.get("limit", limit),
            "pages": (total + limit - 1) // limit if limit > 0 else 0,
        }), 200, _cors_headers()

    @bp.route("/api/admin/subscription/<int:sub_id>", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_subscription_info(request, admin_id, sub_id):
        _ = (request, admin_id)
        sub = await get_subscription_by_id_only(sub_id)
        if not sub:
            return jsonify({"error": "Subscription not found"}), 404, _cors_headers()
        return jsonify({
            "success": True,
            "subscription": {
                "id": sub["id"],
                "name": (sub.get("name") or "").strip() or f"Подписка {sub['id']}",
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
            "servers": [],
        }), 200, _cors_headers()

    @bp.route("/api/admin/subscription/<int:sub_id>/update", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_subscription_update(request, admin_id, sub_id):
        _ = admin_id
        data = await request.get_json(silent=True) or {}
        sub = await get_subscription_by_id_only(sub_id)
        if not sub:
            return jsonify({"error": "Subscription not found"}), 404, _cors_headers()
        if "name" in data:
            await update_subscription_name(sub_id, data["name"])
        if "expires_at" in data:
            await update_subscription_expiry(sub_id, int(data["expires_at"]))
        if "device_limit" in data:
            await update_subscription_device_limit(sub_id, int(data["device_limit"]))
        if data.get("status") == "deleted":
            await update_subscription_status(sub_id, "deleted")
            await clear_subscription_notifications(sub_id)
            subscription_manager = get_ctx().subscription_manager
            if subscription_manager:
                try:
                    await subscription_manager.suspend_access(subscription_id=sub_id)
                except Exception as e:
                    logger.warning("suspend_access failed for %s: %s", sub_id, e)
        updated_sub = await get_subscription_by_id_only(sub_id)
        return jsonify({"success": True, "subscription": updated_sub}), 200, _cors_headers()

    @bp.route("/api/admin/subscription/<int:sub_id>/sync", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_subscription_sync(request, admin_id, sub_id):
        _ = (request, admin_id, sub_id)
        return jsonify({
            "success": False,
            "error": "Manual per-server sync removed in RemnaWave-only mode",
        }), 410, _cors_headers()

    @bp.route("/api/admin/subscription/<int:sub_id>/delete", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_subscription_delete(request, admin_id, sub_id):
        data = await request.get_json(silent=True) or {}
        if not data.get("confirm", False):
            return jsonify({"error": "Confirmation required"}), 400, _cors_headers()
        sub = await get_subscription_by_id_only(sub_id)
        if not sub:
            return jsonify({"error": "Subscription not found"}), 404, _cors_headers()
        await update_subscription_status(sub_id, "deleted")
        await clear_subscription_notifications(sub_id)
        subscription_manager = get_ctx().subscription_manager
        if subscription_manager:
            try:
                await subscription_manager.suspend_access(subscription_id=sub_id)
            except Exception as e:
                logger.warning("suspend_access failed for %s: %s", sub_id, e)
        logger.info("Админ %s пометил подписку %s как deleted", admin_id, sub_id)
        return jsonify({"success": True, "message": "Подписка удалена"}), 200, _cors_headers()

    return bp
