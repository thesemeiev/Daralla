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
        """API endpoint для получения статуса серверов"""
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

            from ....context import get_app_context
            ctx = get_app_context()
            server_manager = ctx.server_manager if ctx else None
            if not server_manager:
                return jsonify({'error': 'Server manager not available'}), 503

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                servers = [
                    {
                        'name': server["name"],
                        'status': 'available',
                    }
                    for server in server_manager.servers
                ]

                return jsonify({
                    'success': True,
                    'servers': servers
                }), 200, {
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
