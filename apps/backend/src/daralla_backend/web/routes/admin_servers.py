"""
Quart Blueprint: admin server-groups, server-group/update, servers-config,
server-config/update, server-config/sync-flow, server-config/delete, sync-all.
"""
from quart import Blueprint, jsonify, request

from daralla_backend.services.admin_servers_service import (
    handle_server_config_delete,
    handle_server_config_sync_flow,
    handle_server_config_update,
    handle_server_group_update,
    handle_server_groups,
    handle_servers_config,
    handle_sync_all,
)
from daralla_backend.web.routes.admin_common import _cors_headers, admin_route


def create_blueprint(bot_app):
    bp = Blueprint("admin_servers", __name__)

    @bp.route("/api/admin/server-groups", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_server_groups(request, admin_id):
        data = await request.get_json(silent=True) or {}
        payload, status = await handle_server_groups(data)
        return jsonify(payload), status, _cors_headers()

    @bp.route("/api/admin/server-group/update", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_server_group_update(request, admin_id):
        data = await request.get_json(silent=True) or {}
        payload, status = await handle_server_group_update(data)
        return jsonify(payload), status, _cors_headers()

    @bp.route("/api/admin/servers-config", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_servers_config(request, admin_id):
        data = await request.get_json(silent=True) or {}
        payload, status = await handle_servers_config(data)
        return jsonify(payload), status, _cors_headers()

    @bp.route("/api/admin/server-config/update", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_server_config_update(request, admin_id):
        data = await request.get_json(silent=True) or {}
        payload, status = await handle_server_config_update(data)
        return jsonify(payload), status, _cors_headers()

    @bp.route("/api/admin/server-config/sync-flow", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_server_config_sync_flow(request, admin_id):
        data = await request.get_json(silent=True) or {}
        payload, status = await handle_server_config_sync_flow(data)
        return jsonify(payload), status, _cors_headers()

    @bp.route("/api/admin/server-config/delete", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_server_config_delete(request, admin_id):
        data = await request.get_json(silent=True) or {}
        payload, status = await handle_server_config_delete(data)
        return jsonify(payload), status, _cors_headers()

    @bp.route("/api/admin/sync-all", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_sync_all(request, admin_id):
        payload, status = await handle_sync_all()
        return jsonify(payload), status, _cors_headers()

    return bp
