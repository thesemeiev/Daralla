"""RemnaWave-only: server/group admin API is deprecated."""

from quart import Blueprint, request, jsonify

from bot.web.routes.admin_common import _cors_headers, admin_route


def create_blueprint(bot_app):
    bp = Blueprint("admin_servers", __name__)

    def _gone():
        return jsonify({
            "success": False,
            "error": "Server/group admin API removed in RemnaWave-only mode",
        }), 410, _cors_headers()

    @bp.route("/api/admin/server-groups", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_server_groups(request, admin_id):
        _ = (request, admin_id)
        return _gone()

    @bp.route("/api/admin/server-group/update", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_server_group_update(request, admin_id):
        _ = (request, admin_id)
        return _gone()

    @bp.route("/api/admin/servers-config", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_servers_config(request, admin_id):
        _ = (request, admin_id)
        return _gone()

    @bp.route("/api/admin/server-config/update", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_server_config_update(request, admin_id):
        _ = (request, admin_id)
        return _gone()

    @bp.route("/api/admin/server-config/sync-flow", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_server_config_sync_flow(request, admin_id):
        _ = (request, admin_id)
        return _gone()

    @bp.route("/api/admin/server-config/delete", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_server_config_delete(request, admin_id):
        _ = (request, admin_id)
        return _gone()

    @bp.route("/api/admin/sync-all", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_sync_all(request, admin_id):
        return jsonify({
            "success": False,
            "error": "Sync API removed in RemnaWave-only mode",
        }), 410, _cors_headers()

    return bp
