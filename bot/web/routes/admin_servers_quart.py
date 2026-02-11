"""
Quart Blueprint: admin server-groups, server-group/update, servers-config,
server-config/update, server-config/sync-flow, server-config/delete, sync-all.
"""
import logging

from quart import Blueprint, request, jsonify

from bot.web.routes.admin_common import CORS_HEADERS, _cors_headers, require_admin
from bot.db.servers_db import (
    get_server_groups,
    add_server_group,
    get_group_load_statistics,
    update_server_group,
    get_servers_config,
    add_server_config,
    get_server_by_id,
    update_server_config,
    delete_server_config,
)
from bot.services.server_provider import ServerProvider
from bot.services.xui_service import X3
from bot.handlers.webhooks.webhook_auth import get_bot_module

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint("admin_servers", __name__)

    @bp.route("/api/admin/server-groups", methods=["POST", "OPTIONS"])
    async def api_admin_server_groups():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            _, err = await require_admin(request)
            if err:
                return err
            data = await request.get_json(silent=True) or {}
            action = data.get("action", "list")
            if action == "list":
                groups = await get_server_groups(only_active=False)
                stats = await get_group_load_statistics()
                return jsonify({"success": True, "groups": groups, "stats": stats}), 200, _cors_headers()
            elif action == "add":
                name = data.get("name")
                description = data.get("description")
                is_default = data.get("is_default", False)
                if not name:
                    return jsonify({"error": "Name is required"}), 400, _cors_headers()
                group_id = await add_server_group(name, description, is_default)
                return jsonify({"success": True, "group_id": group_id}), 200, _cors_headers()
            return jsonify({"error": "Invalid action"}), 400, _cors_headers()
        except Exception as e:
            logger.error("Ошибка в /api/admin/server-groups: %s", e, exc_info=True)
            return jsonify({"error": str(e)}), 500, _cors_headers()

    @bp.route("/api/admin/server-group/update", methods=["POST", "OPTIONS"])
    async def api_admin_server_group_update():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            _, err = await require_admin(request)
            if err:
                return err
            data = await request.get_json(silent=True) or {}
            group_id = data.get("id")
            if not group_id:
                return jsonify({"error": "Group ID is required"}), 400, _cors_headers()
            await update_server_group(
                group_id,
                name=data.get("name"),
                description=data.get("description"),
                is_active=data.get("is_active"),
                is_default=data.get("is_default"),
            )
            return jsonify({"success": True}), 200, _cors_headers()
        except Exception as e:
            logger.error("Ошибка в /api/admin/server-group/update: %s", e, exc_info=True)
            return jsonify({"error": str(e)}), 500, _cors_headers()

    @bp.route("/api/admin/servers-config", methods=["POST", "OPTIONS"])
    async def api_admin_servers_config():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            _, err = await require_admin(request)
            if err:
                return err
            data = await request.get_json(silent=True) or {}
            action = data.get("action", "list")
            if action == "list":
                group_id = data.get("group_id")
                servers = await get_servers_config(group_id=group_id, only_active=False)
                return jsonify({"success": True, "servers": servers}), 200, _cors_headers()
            elif action == "add":
                group_id = data.get("group_id")
                name = data.get("name")
                host = data.get("host")
                login = data.get("login")
                password = data.get("password")
                if not all([group_id, name, host, login, password]):
                    return jsonify({"error": "All fields are required"}), 400, _cors_headers()
                server_id = await add_server_config(
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
                )
                try:
                    bot_module = get_bot_module()
                    server_manager = getattr(bot_module, "server_manager", None) if bot_module else None
                    if server_manager:
                        new_config = await ServerProvider.get_all_servers_by_location()
                        server_manager.init_from_config(new_config)
                except Exception as mgr_e:
                    logger.error("Ошибка обновления менеджера серверов: %s", mgr_e)
                return jsonify({"success": True, "server_id": server_id}), 200, _cors_headers()
            return jsonify({"error": "Invalid action"}), 400, _cors_headers()
        except Exception as e:
            logger.error("Ошибка в /api/admin/servers-config: %s", e, exc_info=True)
            return jsonify({"error": str(e)}), 500, _cors_headers()

    @bp.route("/api/admin/server-config/update", methods=["POST", "OPTIONS"])
    async def api_admin_server_config_update():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            _, err = await require_admin(request)
            if err:
                return err
            data = await request.get_json(silent=True) or {}
            server_id = data.get("id")
            if not server_id:
                return jsonify({"error": "Server ID is required"}), 400, _cors_headers()
            update_data = {k: v for k, v in data.items() if k not in ("initData", "id")}
            old_server = await get_server_by_id(int(server_id))
            old_flow = ((old_server.get("client_flow") or "").strip() or None) if old_server else None
            new_flow = (update_data.get("client_flow") or "").strip() or None
            client_flow_changed = old_flow != new_flow
            await update_server_config(server_id, **update_data)
            try:
                bot_module = get_bot_module()
                server_manager = getattr(bot_module, "server_manager", None) if bot_module else None
                if server_manager:
                    new_config = await ServerProvider.get_all_servers_by_location()
                    server_manager.init_from_config(new_config)
            except Exception as mgr_e:
                logger.error("Ошибка обновления менеджера серверов: %s", mgr_e)
            return jsonify({
                "success": True,
                "client_flow_changed": client_flow_changed,
                "server_id": int(server_id),
            }), 200, _cors_headers()
        except Exception as e:
            logger.error("Ошибка в /api/admin/server-config/update: %s", e, exc_info=True)
            return jsonify({"error": str(e)}), 500, _cors_headers()

    @bp.route("/api/admin/server-config/sync-flow", methods=["POST", "OPTIONS"])
    async def api_admin_server_config_sync_flow():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            _, err = await require_admin(request)
            if err:
                return err
            data = await request.get_json(silent=True) or {}
            server_id = data.get("server_id") or data.get("id")
            if not server_id:
                return jsonify({"error": "server_id is required"}), 400, _cors_headers()
            server = await get_server_by_id(int(server_id))
            if not server:
                return jsonify({"error": "Server not found"}), 404, _cors_headers()
            x3 = X3(
                login=server["login"],
                password=server["password"],
                host=server["host"],
                vpn_host=server.get("vpn_host"),
                subscription_port=server.get("subscription_port", 2096),
                subscription_url=server.get("subscription_url"),
            )
            flow_val = (server.get("client_flow") or "").strip() or ""
            updated, errs = await x3.sync_flow_for_all_clients(flow_val)
            return jsonify({
                "success": True,
                "updated": updated,
                "errors": errs[:20],
            }), 200, _cors_headers()
        except Exception as e:
            logger.exception("sync-flow error")
            return jsonify({"error": str(e)}), 500, _cors_headers()

    @bp.route("/api/admin/server-config/delete", methods=["POST", "OPTIONS"])
    async def api_admin_server_config_delete():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            _, err = await require_admin(request)
            if err:
                return err
            data = await request.get_json(silent=True) or {}
            server_id = data.get("id")
            if not server_id:
                return jsonify({"error": "Server ID is required"}), 400, _cors_headers()
            await delete_server_config(server_id)
            return jsonify({"success": True}), 200, _cors_headers()
        except Exception as e:
            logger.error("Ошибка в /api/admin/server-config/delete: %s", e, exc_info=True)
            return jsonify({"error": str(e)}), 500, _cors_headers()

    @bp.route("/api/admin/sync-all", methods=["POST", "OPTIONS"])
    async def api_admin_sync_all():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            _, err = await require_admin(request)
            if err:
                return err
            bot_module = get_bot_module()
            sync_manager = getattr(bot_module, "sync_manager", None) if bot_module else None
            if not sync_manager:
                return jsonify({"error": "Sync manager not available"}), 503, _cors_headers()
            stats = await sync_manager.sync_all_subscriptions(auto_fix=True)
            return jsonify({"success": True, "stats": stats}), 200, _cors_headers()
        except Exception as e:
            logger.error("Ошибка в /api/admin/sync-all: %s", e, exc_info=True)
            return jsonify({"error": str(e)}), 500, _cors_headers()

    return bp
