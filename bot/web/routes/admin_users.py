"""
Quart Blueprint: POST /api/admin/users, user/<id>, user/<id>/create-subscription, user/<id>/delete.
"""
import logging
from quart import Blueprint, request, jsonify

from bot.web.routes.admin_common import _cors_headers, admin_route
from bot.services.admin_users_service import (
    create_subscription_for_user,
    delete_user_and_clients,
    get_user_info_payload,
    get_users_list,
)

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint("admin_users", __name__)

    @bp.route("/api/admin/users", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_users(request, admin_id):
        data = await request.get_json(silent=True) or {}
        search = data.get("search", "").strip()
        page = int(data.get("page", 1))
        limit = int(data.get("limit", 20))
        users, total = await get_users_list(search, page, limit)
        return jsonify({
            "success": True,
            "users": users,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit if limit > 0 else 0,
        }), 200, _cors_headers()

    @bp.route("/api/admin/user/<user_id_param>", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_user_info(request, admin_id, user_id_param):
        payload = await get_user_info_payload(user_id_param)
        if not payload:
            return jsonify({"error": "User not found"}), 404, _cors_headers()
        return jsonify({
            "success": True,
            "user": payload["user"],
            "subscriptions": payload["subscriptions"],
            "payments": payload["payments"],
        }), 200, _cors_headers()

    @bp.route("/api/admin/user/<user_id_param>/create-subscription", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_user_create_subscription(request, admin_id, user_id_param):
        data = await request.get_json(silent=True) or {}
        period = data.get("period", "month")
        device_limit = int(data.get("device_limit", 1))
        name = data.get("name") or None
        expires_at = data.get("expires_at")
        payload, err_body, err_code = await create_subscription_for_user(
            user_id_param=user_id_param,
            period=period,
            device_limit=device_limit,
            name=name,
            expires_at=expires_at,
        )
        if err_body:
            return jsonify(err_body), err_code, _cors_headers()

        return jsonify({
            "success": True,
            "subscription": payload["subscription"],
            "successful_servers": payload["successful_servers"],
            "failed_servers": payload["failed_servers"],
        }), 200, _cors_headers()

    @bp.route("/api/admin/user/<user_id_param>/delete", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_user_delete(request, admin_id, user_id_param):
        data = await request.get_json(silent=True) or {}
        confirm = data.get("confirm", False)
        if not confirm:
            return jsonify({"error": "Confirmation required"}), 400, _cors_headers()
        payload, err_body, err_code = await delete_user_and_clients(user_id_param)
        if err_body:
            return jsonify(err_body), err_code, _cors_headers()
        logger.info("Админ %s удалил пользователя %s", admin_id, user_id_param)
        return jsonify({
            "success": True,
            "stats": payload["stats"],
            "deleted_servers": payload["deleted_servers"],
            "failed_servers": payload["failed_servers"],
        }), 200, _cors_headers()

    return bp
