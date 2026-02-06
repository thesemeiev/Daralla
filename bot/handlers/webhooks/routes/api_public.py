"""
Blueprint: GET /api/prices, /api/servers.
"""
import logging
from flask import Blueprint, request

from ..webhook_utils import APIResponse, handle_options, run_async

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint('api_public', __name__)

    @bp.route('/api/prices', methods=['GET', 'OPTIONS'])
    def api_prices():
        """API endpoint для получения цен (публичный, без авторизации)"""
        if request.method == 'OPTIONS':
            return handle_options()
        try:
            from ....prices_config import PRICES
            return APIResponse.success(
                prices=PRICES,
                month=PRICES.get('month', 150),
                **{'3month': PRICES.get('3month', 350)}
            )
        except Exception as e:
            logger.error(f"Ошибка в API /api/prices: {e}", exc_info=True)
            return APIResponse.internal_error()

    @bp.route('/api/servers', methods=['GET', 'OPTIONS'])
    def api_servers():
        """API endpoint для получения статуса серверов. При Remnawave — ноды из API."""
        if request.method == 'OPTIONS':
            return handle_options()
        try:
            async def fetch_servers():
                from ....services.remnawave_service import is_remnawave_configured
                from ....services.nodes_display_service import get_remnawave_nodes_for_display

                if is_remnawave_configured():
                    nodes = await get_remnawave_nodes_for_display()
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
                return APIResponse.success(servers=servers)
            return run_async(fetch_servers())
        except Exception as e:
            logger.error(f"Ошибка в API /api/servers: {e}", exc_info=True)
            return APIResponse.internal_error()

    return bp
