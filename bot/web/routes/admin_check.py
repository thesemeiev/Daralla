"""
Quart Blueprint: POST /api/admin/check (admin rights check).
"""
from quart import Blueprint, jsonify

from bot.web.routes.admin_common import _cors_headers, admin_route
from bot.handlers.webhooks.webhook_auth import check_admin_access_async


def create_blueprint(bot_app):
    bp = Blueprint("admin_check", __name__)

    @bp.route("/api/admin/check", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_check(request, admin_id):
        is_admin = await check_admin_access_async(admin_id)
        return jsonify({"success": True, "is_admin": is_admin}), 200, _cors_headers()

    return bp
