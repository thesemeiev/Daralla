"""
Quart Blueprint: GET /api/prices, GET /api/servers (public API for Mini App).
"""
import logging

from quart import Blueprint, request, jsonify

from bot.handlers.api_support.webhook_auth import authenticate_request_async

logger = logging.getLogger(__name__)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Content-Type": "application/json",
}
CORS_OPTIONS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "*",
}


def create_blueprint(bot_app):
    bp = Blueprint("api_public", __name__)

    @bp.route("/api/prices", methods=["GET", "OPTIONS"])
    async def api_prices():
        """API endpoint для получения цен (публичный, без авторизации)."""
        if request.method == "OPTIONS":
            return "", 200, CORS_OPTIONS_HEADERS
        try:
            from bot.prices_config import PRICES
            return jsonify({
                "success": True, "prices": PRICES,
                "month": PRICES.get("month", 150), "3month": PRICES.get("3month", 350),
            }), 200, CORS_HEADERS
        except Exception as e:
            logger.error("Ошибка в API /api/prices: %s", e, exc_info=True)
            return jsonify({
                "success": True, "prices": {"month": 150, "3month": 350}, "month": 150, "3month": 350,
            }), 200, CORS_HEADERS

    @bp.route("/api/servers", methods=["GET", "OPTIONS"])
    async def api_servers():
        """RemnaWave-only mode: legacy server status API removed."""
        if request.method == "OPTIONS":
            return "", 200, CORS_OPTIONS_HEADERS
        try:
            user_id = await authenticate_request_async(request.headers, request.args, {}, request.cookies)
            if not user_id:
                return jsonify({"error": "Invalid authentication"}), 401, CORS_HEADERS

            return jsonify({"success": True, "servers": []}), 200, CORS_HEADERS

        except Exception as e:
            logger.error("Ошибка в API /api/servers: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500, CORS_HEADERS

    return bp
