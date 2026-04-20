"""
Quart Blueprint: POST /api/admin/broadcast (broadcast message to users).
"""
from quart import Blueprint, request, jsonify

from bot.services.admin_broadcast_service import resolve_broadcast_recipients, send_broadcast
from bot.web.routes.admin_common import _cors_headers, admin_route


def create_blueprint(bot_app):
    bp = Blueprint("admin_broadcast", __name__)

    @bp.route("/api/admin/broadcast", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_broadcast(request, admin_id):
        data = await request.get_json(silent=True) or {}
        message_text = (data.get("message") or "").strip()
        if not message_text:
            return jsonify({"error": "Message text is required"}), 400, _cors_headers()

        user_ids = data.get("user_ids", [])
        recipients = await resolve_broadcast_recipients(user_ids)
        bot = bot_app.bot
        payload = await send_broadcast(bot, recipients, message_text)
        return jsonify(payload), 200, _cors_headers()

    return bp
