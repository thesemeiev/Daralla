"""
Quart Blueprint: GET/POST /api/admin/commerce — цены и лимит устройств по умолчанию.
"""
from quart import Blueprint, request, jsonify

from bot.services.admin_commerce_service import (
    admin_commerce_get_payload,
    admin_commerce_update_payload,
)
from bot.web.routes.admin_common import _cors_headers, admin_route


def create_blueprint(bot_app):
    bp = Blueprint("admin_commerce", __name__)

    @bp.route("/api/admin/commerce", methods=["GET", "POST", "OPTIONS"])
    @admin_route
    async def api_admin_commerce(request, admin_id):
        if request.method == "GET":
            payload, status = await admin_commerce_get_payload()
            return jsonify(payload), status, _cors_headers()

        data = await request.get_json(silent=True) or {}
        payload, status = await admin_commerce_update_payload(data)
        return jsonify(payload), status, _cors_headers()

    return bp
