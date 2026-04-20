"""
Quart Blueprint: POST /api/admin/subscription/<id>, .../update, .../sync, .../delete.
"""
import logging

from quart import Blueprint, request, jsonify

from bot.web.routes.admin_common import _cors_headers, admin_route
from bot.services.admin_subscriptions_flow_service import (
    delete_subscription_payload,
    list_subscriptions_payload,
    manual_sync_payload,
    subscription_info_payload,
    update_subscription_payload,
)

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint("admin_subscriptions", __name__)

    @bp.route("/api/admin/subscriptions", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_subscriptions(request, admin_id):
        """
        Возвращает страницу подписок для админки с базовыми фильтрами.
        """
        data = await request.get_json(silent=True) or {}
        try:
            page = int(data.get("page", 1))
        except (TypeError, ValueError):
            page = 1
        try:
            limit = int(data.get("limit", 20))
        except (TypeError, ValueError):
            limit = 20

        status = (data.get("status") or "").strip() or None
        owner_query = (data.get("owner_query") or "").strip() or None
        long_only = bool(data.get("long_only", False))
        payload = await list_subscriptions_payload(page=page, limit=limit, status=status, owner_query=owner_query, long_only=long_only)
        return jsonify(payload), 200, _cors_headers()

    @bp.route("/api/admin/subscription/<int:sub_id>", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_subscription_info(request, admin_id, sub_id):
        await request.get_json(silent=True) or {}
        payload = await subscription_info_payload(sub_id)
        if not payload:
            return jsonify({"error": "Subscription not found"}), 404, _cors_headers()
        return jsonify(payload), 200, _cors_headers()

    @bp.route("/api/admin/subscription/<int:sub_id>/update", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_subscription_update(request, admin_id, sub_id):
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
        payload, err_body, err_code = await update_subscription_payload(sub_id=sub_id, updates=updates, logger=logger)
        if err_body:
            return jsonify(err_body), err_code, _cors_headers()
        return jsonify(payload), 200, _cors_headers()

    @bp.route("/api/admin/subscription/<int:sub_id>/sync", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_subscription_sync(request, admin_id, sub_id):
        await request.get_json(silent=True) or {}
        payload, err_body, err_code = await manual_sync_payload(sub_id=sub_id, logger=logger)
        if err_body:
            return jsonify(err_body), err_code, _cors_headers()
        return jsonify(payload), 200, _cors_headers()

    @bp.route("/api/admin/subscription/<int:sub_id>/delete", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_subscription_delete(request, admin_id, sub_id):
        data = await request.get_json(silent=True) or {}
        if not data.get("confirm", False):
            return jsonify({"error": "Confirmation required"}), 400, _cors_headers()
        payload, err_body, err_code = await delete_subscription_payload(sub_id=sub_id)
        if err_body:
            return jsonify(err_body), err_code, _cors_headers()
        logger.info("Админ %s удалил подписку %s", admin_id, sub_id)
        return jsonify(payload), 200, _cors_headers()

    return bp
