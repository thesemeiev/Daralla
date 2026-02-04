"""
Маршруты: группы серверов, конфигурация серверов, синхронизация.
"""
import asyncio
import logging

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
    @bp.route("/api/admin/server-groups", methods=["POST", "OPTIONS"])
    def api_admin_server_groups():
        if request.method == "OPTIONS":
            return options_response()
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({"error": "Access denied"}), 403
            data = request.get_json(silent=True) or {}
            from .....db import add_server_group, get_group_load_statistics, get_server_groups

            action = data.get("action", "list")
            if action == "list":
                groups = _run_async(get_server_groups(only_active=False))
                stats = _run_async(get_group_load_statistics())
                return jsonify({"success": True, "groups": groups, "stats": stats})
            if action == "add":
                name = data.get("name")
                description = data.get("description")
                is_default = data.get("is_default", False)
                if not name:
                    return jsonify({"error": "Name is required"}), 400
                group_id = _run_async(add_server_group(name, description, is_default))
                return jsonify({"success": True, "group_id": group_id})
            return jsonify({"error": "Unknown action"}), 400
        except Exception as e:
            logger.error("Ошибка в /api/admin/server-groups: %s", e)
            return jsonify({"error": str(e)}), 500

    @bp.route("/api/admin/server-group/update", methods=["POST", "OPTIONS"])
    def api_admin_server_group_update():
        if request.method == "OPTIONS":
            return options_response()
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({"error": "Access denied"}), 403
            data = request.get_json(silent=True) or {}
            group_id = data.get("id")
            if not group_id:
                return jsonify({"error": "Group ID is required"}), 400
            from .....db import update_server_group

            _run_async(update_server_group(
                group_id,
                name=data.get("name"),
                description=data.get("description"),
                is_active=data.get("is_active"),
                is_default=data.get("is_default"),
            ))
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @bp.route("/api/admin/servers-config", methods=["POST", "OPTIONS"])
    def api_admin_servers_config():
        if request.method == "OPTIONS":
            return options_response()
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({"error": "Access denied"}), 403
            data = request.get_json(silent=True) or {}
            from .....db import add_server_config, get_servers_config
            from .....services.server_provider import ServerProvider

            action = data.get("action", "list")
            if action == "list":
                group_id = data.get("group_id")
                servers = _run_async(get_servers_config(group_id=group_id, only_active=False))
                return jsonify({"success": True, "servers": servers})
            if action == "add":
                group_id = data.get("group_id")
                name = data.get("name")
                host = data.get("host")
                login = data.get("login")
                password = data.get("password")
                if not all([group_id, name, host, login, password]):
                    return jsonify({"error": "All fields are required"}), 400
                server_id = _run_async(add_server_config(
                    group_id,
                    name,
                    host,
                    login,
                    password,
                    display_name=data.get("display_name"),
                    vpn_host=data.get("vpn_host"),
                    lat=data.get("lat"),
                    lng=data.get("lng"),
                    subscription_port=data.get("subscription_port"),
                    subscription_url=data.get("subscription_url") or None,
                    client_flow=data.get("client_flow") or None,
                    map_label=data.get("map_label") or None,
                    location=data.get("location") or None,
                    max_concurrent_clients=data.get("max_concurrent_clients"),
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
            from .....db import get_server_by_id, update_server_config
            from .....services.server_provider import ServerProvider

            update_data = {k: v for k, v in data.items() if k not in ("initData", "id")}
            old_server = _run_async(get_server_by_id(int(server_id)))
            old_flow = (old_server.get("client_flow") or "").strip() or None if old_server else None
            new_flow = (update_data.get("client_flow") or "").strip() or None
            client_flow_changed = old_flow != new_flow

            _run_async(update_server_config(server_id, **update_data))
            try:
                from .....bot import server_manager
                new_config = _run_async(ServerProvider.get_all_servers_by_location())
                if server_manager:
                    server_manager.init_from_config(new_config)
            except Exception as mgr_e:
                logger.error("Ошибка обновления менеджера серверов: %s", mgr_e)
            return jsonify({"success": True, "client_flow_changed": client_flow_changed, "server_id": int(server_id)})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @bp.route("/api/admin/server-config/sync-flow", methods=["POST", "OPTIONS"])
    def api_admin_server_config_sync_flow():
        if request.method == "OPTIONS":
            return options_response()
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({"error": "Access denied"}), 403
            data = request.get_json(silent=True) or {}
            server_id = data.get("server_id") or data.get("id")
            if not server_id:
                return jsonify({"error": "server_id is required"}), 400
            from .....db import get_server_by_id
            from .....services.xui_service import X3

            server = _run_async(get_server_by_id(int(server_id)))
            if not server:
                return jsonify({"error": "Server not found"}), 404
            x3 = X3(
                login=server["login"],
                password=server["password"],
                host=server["host"],
                vpn_host=server.get("vpn_host"),
                subscription_port=server.get("subscription_port", 2096),
                subscription_url=server.get("subscription_url"),
            )
            flow_val = (server.get("client_flow") or "").strip() or ""
            updated, errs = x3.sync_flow_for_all_clients(flow_val)
            return jsonify({"success": True, "updated": updated, "errors": errs[:20]})
        except Exception as e:
            logger.exception("sync-flow error")
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

    @bp.route("/api/admin/sync-all", methods=["POST", "OPTIONS"])
    def api_admin_sync_all():
        if request.method == "OPTIONS":
            return options_response()
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({"error": "Access denied"}), 403
            from ...context import get_app_context

            ctx = get_app_context()
            sync_manager = ctx.sync_manager if ctx else None
            if not sync_manager:
                return jsonify({"success": True, "stats": {"message": "Remnawave mode: sync skipped"}})
            stats = _run_async(sync_manager.sync_all_subscriptions(auto_fix=True))
            return jsonify({"success": True, "stats": stats})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
