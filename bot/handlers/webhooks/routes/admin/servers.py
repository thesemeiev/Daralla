"""
Маршруты: маркеры на карте (название + положение).
"""
import asyncio
import logging
import time

from flask import request, jsonify

from ...webhook_auth import authenticate_request, check_admin_access
from ._common import CORS_HEADERS, options_response

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def register_servers_routes(bp):
    @bp.route("/api/admin/servers-config", methods=["POST", "OPTIONS"])
    def api_admin_servers_config():
        if request.method == "OPTIONS":
            return options_response()
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({"error": "Access denied"}), 403
            data = request.get_json(silent=True) or {}
            from .....db import add_server_config, get_servers_config, get_or_create_default_group
            from .....services.server_provider import ServerProvider

            action = data.get("action", "list")
            if action == "list":
                servers = _run_async(get_servers_config(group_id=None, only_active=False))
                return jsonify({"success": True, "servers": servers})
            if action == "add":
                display_name = (data.get("display_name") or data.get("name") or "").strip()
                lat = data.get("lat")
                lng = data.get("lng")
                if not display_name:
                    return jsonify({"error": "Название обязательно"}), 400
                if lat is None and lng is None:
                    return jsonify({"error": "Укажите широту и долготу"}), 400
                try:
                    lat_f = float(lat) if lat is not None else 0.0
                    lng_f = float(lng) if lng is not None else 0.0
                except (TypeError, ValueError):
                    return jsonify({"error": "Некорректные координаты"}), 400
                group_id = _run_async(get_or_create_default_group())
                name = f"m{int(time.time() * 1000)}"
                server_id = _run_async(add_server_config(
                    group_id,
                    name,
                    host="",
                    login="",
                    password="",
                    display_name=display_name,
                    vpn_host=None,
                    lat=lat_f,
                    lng=lng_f,
                    subscription_port=2096,
                    subscription_url=None,
                    client_flow=None,
                    map_label=display_name,
                    location=display_name,
                    max_concurrent_clients=50,
                ))
                try:
                    from .....bot import server_manager
                    new_config = _run_async(ServerProvider.get_all_servers_by_location())
                    if server_manager:
                        server_manager.init_from_config(new_config)
                except Exception as mgr_e:
                    logger.error("Ошибка обновления менеджера серверов: %s", mgr_e)
                return jsonify({"success": True, "server_id": server_id})
            return jsonify({"error": "Unknown action"}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @bp.route("/api/admin/server-config/update", methods=["POST", "OPTIONS"])
    def api_admin_server_config_update():
        if request.method == "OPTIONS":
            return options_response()
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({"error": "Access denied"}), 403
            data = request.get_json(silent=True) or {}
            server_id = data.get("id")
            if not server_id:
                return jsonify({"error": "Server ID is required"}), 400
            from .....db import update_server_config
            from .....services.server_provider import ServerProvider

            update_data = {k: v for k, v in data.items() if k not in ("initData", "id")}

            _run_async(update_server_config(server_id, **update_data))
            try:
                from .....bot import server_manager
                new_config = _run_async(ServerProvider.get_all_servers_by_location())
                if server_manager:
                    server_manager.init_from_config(new_config)
            except Exception as mgr_e:
                logger.error("Ошибка обновления менеджера серверов: %s", mgr_e)
            return jsonify({"success": True, "server_id": int(server_id)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @bp.route("/api/admin/server-config/delete", methods=["POST", "OPTIONS"])
    def api_admin_server_config_delete():
        if request.method == "OPTIONS":
            return options_response()
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({"error": "Access denied"}), 403
            data = request.get_json(silent=True) or {}
            server_id = data.get("id")
            if not server_id:
                return jsonify({"error": "Server ID is required"}), 400
            from .....db import delete_server_config

            _run_async(delete_server_config(server_id))
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

