"""
Blueprint: GET /api/servers (server status for Mini App).
"""
import asyncio
import datetime
import logging
from flask import Blueprint, request, jsonify

from ..webhook_auth import authenticate_request

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint('api_public', __name__)

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

            def get_server_manager():
                try:
                    from .... import bot as bot_module
                    return getattr(bot_module, 'server_manager', None)
                except (ImportError, AttributeError):
                    return None

            server_manager = get_server_manager()
            if not server_manager:
                return jsonify({'error': 'Server manager not available'}), 503

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                health_results = server_manager.check_all_servers_health(force_check=False)
                health_status = server_manager.get_server_health_status()

                servers = []
                for server in server_manager.servers:
                    server_name = server["name"]
                    is_healthy = health_results.get(server_name, False)
                    status_info = health_status.get(server_name, {})

                    last_check = None
                    if status_info.get('last_check'):
                        if isinstance(status_info['last_check'], (int, float)):
                            last_check = datetime.datetime.fromtimestamp(status_info['last_check']).strftime('%d.%m.%Y %H:%M')
                        else:
                            last_check = str(status_info['last_check'])

                    servers.append({
                        'name': server_name,
                        'status': 'online' if is_healthy else 'offline',
                        'last_check': last_check
                    })

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
