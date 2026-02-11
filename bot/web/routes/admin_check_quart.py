"""
Quart Blueprint: POST /api/admin/check (admin rights check).
"""
import logging

from quart import Blueprint, request, jsonify

from bot.web.routes.admin_common import CORS_HEADERS, _cors_headers, require_admin
from bot.handlers.webhooks.webhook_auth import check_admin_access_async

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint("admin_check", __name__)

    @bp.route("/api/admin/check", methods=["POST", "OPTIONS"])
    async def api_admin_check():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            user_id, err = await require_admin(request)
            if err:
                return err
            is_admin = await check_admin_access_async(user_id)
            return jsonify({"success": True, "is_admin": is_admin}), 200, _cors_headers()
        except Exception as e:
            logger.error("Ошибка в /api/admin/check: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500, _cors_headers()

    return bp
