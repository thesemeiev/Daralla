"""
Quart Blueprint: POST /api/admin/stats (dashboard statistics).
"""
import logging
from quart import Blueprint, request, jsonify

from bot.web.routes.admin_common import _cors_headers, admin_route
from bot.services.admin_stats_service import admin_stats_payload

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint("admin_stats", __name__)

    @bp.route("/api/admin/stats", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_stats(request, admin_id):
        try:
            await request.get_json(silent=True) or {}
        except Exception as json_e:
            logger.warning("Ошибка парсинга JSON в /api/admin/stats: %s", json_e)
        payload = await admin_stats_payload()
        return jsonify(payload), 200, _cors_headers()

    return bp
