"""
Quart Blueprint: POST /api/admin/stats (dashboard statistics).
"""
import logging
from quart import Blueprint, request, jsonify

from daralla_backend.web.routes.admin_common import _cors_headers, admin_route
from daralla_backend.services.admin_stats_service import admin_stats_payload

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint("admin_stats", __name__)

    @bp.route("/api/admin/stats", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_stats(request, admin_id):
        data = {}
        try:
            data = await request.get_json(silent=True) or {}
        except Exception as json_e:
            logger.warning("Ошибка парсинга JSON в /api/admin/stats: %s", json_e)
        revenue_range = data.get("revenue_range")
        if revenue_range is not None and not isinstance(revenue_range, dict):
            revenue_range = None
        payload = await admin_stats_payload(revenue_range=revenue_range)
        return jsonify(payload), 200, _cors_headers()

    return bp
