"""
Quart Blueprint: POST /api/admin/charts/* (user-growth, server-load, conversion, notifications, subscriptions).
"""
import logging

from quart import Blueprint, request, jsonify

from bot.web.routes.admin_common import _cors_headers, admin_route
from bot.services.admin_charts_service import (
    conversion_payload,
    notifications_payload,
    server_load_payload,
    subscriptions_payload,
    user_growth_payload,
)

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint("admin_charts", __name__)

    @bp.route("/api/admin/charts/user-growth", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_charts_user_growth(request, admin_id):
        data = await request.get_json(silent=True) or {}
        days = int(data.get("days", 30))
        payload = await user_growth_payload(days)
        return jsonify(payload), 200, _cors_headers()

    @bp.route("/api/admin/charts/server-load", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_charts_server_load(request, admin_id):
        await request.get_json(silent=True) or {}
        payload = await server_load_payload()
        return jsonify(payload), 200, _cors_headers()

    @bp.route("/api/admin/charts/conversion", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_charts_conversion(request, admin_id):
        data = await request.get_json(silent=True) or {}
        days = int(data.get("days", 30))
        payload = await conversion_payload(days)
        return jsonify(payload), 200, _cors_headers()

    @bp.route("/api/admin/charts/notifications", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_charts_notifications(request, admin_id):
        data = await request.get_json(silent=True) or {}
        days = int(data.get("days", 7))
        payload = await notifications_payload(days)
        return jsonify(payload), 200, _cors_headers()

    @bp.route("/api/admin/charts/subscriptions", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_charts_subscriptions(request, admin_id):
        data = await request.get_json(silent=True) or {}
        days = int(data.get("days", 30))
        payload = await subscriptions_payload(days)
        return jsonify(payload), 200, _cors_headers()

    return bp
