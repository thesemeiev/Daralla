"""
Blueprint: GET /api/servers (server list for Mini App).
"""
import asyncio
import logging
from flask import Blueprint, request, jsonify

from ..webhook_auth import authenticate_request

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint('api_public', __name__)

    @bp.route('/api/prices', methods=['GET', 'OPTIONS'])
    def api_prices():
        """API endpoint для получения цен (публичный, без авторизации)"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
        try:
            from ....prices_config import PRICES
            return jsonify({
                'success': True,
                'prices': PRICES,
                'month': PRICES.get('month', 150),
                '3month': PRICES.get('3month', 350),
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json",
            }
        except Exception as e:
            logger.error(f"Ошибка в API /api/prices: {e}", exc_info=True)
            return jsonify({'success': True, 'prices': {'month': 150, '3month': 350}, 'month': 150, '3month': 350}), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json",
            }

    @bp.route('/api/servers', methods=['GET', 'OPTIONS'])
    def api_servers():
        """API endpoint для получения статуса серверов. При Remnawave — ноды из API."""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })

        try:
            user_id = authenticate_request()
            if not user_id:
                return jsonify({'error': 'Invalid authentication'}), 401

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from ....services.remnawave_service import is_remnawave_configured
                from ....services.nodes_display_service import get_remnawave_nodes_for_display

                if is_remnawave_configured():
                    nodes = loop.run_until_complete(get_remnawave_nodes_for_display())
                    servers = [
                        {
                            "name": n.get("display_name", n.get("name")),
                            "status": n.get("status", "offline"),
                            "display_name": n.get("display_name"),
                            "location": n.get("location"),
                            "uuid": n.get("uuid"),
                        }
                        for n in nodes
                    ]
                else:
                    servers = []

                return jsonify({'success': True, 'servers': servers}), 200, {
                    "Access-Control-Allow-Origin": "*",
                    "Content-Type": "application/json"
                }
            finally:
                loop.close()

        except Exception as e:
            logger.error(f"Ошибка в API /api/servers: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }

    return bp
