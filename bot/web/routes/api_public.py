"""
Quart Blueprint: GET /api/prices, GET /api/servers (public API for Mini App).
"""
import datetime
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
        """API endpoint для получения статуса серверов."""
        if request.method == "OPTIONS":
            return "", 200, CORS_OPTIONS_HEADERS
        try:
            user_id = await authenticate_request_async(request.headers, request.args, {})
            if not user_id:
                return jsonify({"error": "Invalid authentication"}), 401, CORS_HEADERS

            from bot.handlers.api_support.webhook_auth import get_server_manager
            server_manager = get_server_manager()
            if not server_manager:
                return jsonify({"error": "Server manager not available"}), 503, CORS_HEADERS

            health_results = await server_manager.check_all_servers_health(force_check=True)
            health_status = server_manager.get_server_health_status()

            servers = []
            for server in server_manager.servers:
                server_name = server["name"]
                is_healthy = health_results.get(server_name, False)
                status_info = health_status.get(server_name, {})

                last_check = None
                if status_info.get("last_check"):
                    if isinstance(status_info["last_check"], (int, float)):
                        last_check = datetime.datetime.fromtimestamp(status_info["last_check"]).strftime("%d.%m.%Y %H:%M")
                    else:
                        last_check = str(status_info["last_check"])

                servers.append({
                    "name": server_name,
                    "status": "online" if is_healthy else "offline",
                    "last_check": last_check,
                })

            return jsonify({"success": True, "servers": servers}), 200, CORS_HEADERS

        except Exception as e:
            logger.error("Ошибка в API /api/servers: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500, CORS_HEADERS

    return bp
