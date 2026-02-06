"""
Маршруты: ноды Remnawave на карте — список и настройка расположения.
"""
import asyncio
import logging

from flask import request, jsonify

from ...webhook_auth import authenticate_request, check_admin_access
from ._common import options_response

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def register_servers_routes(bp):
    @bp.route("/api/admin/nodes", methods=["GET", "OPTIONS"])
    def api_admin_nodes():
        """Список нод Remnawave (с координатами и переопределениями)."""
        if request.method == "OPTIONS":
            return options_response()
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({"error": "Access denied"}), 403
            from .....services.remnawave_service import is_remnawave_configured
            from .....services.nodes_display_service import get_remnawave_nodes_for_display

            if not is_remnawave_configured():
                return jsonify({"success": True, "nodes": [], "remnawave": False})
            nodes = _run_async(get_remnawave_nodes_for_display())
            return jsonify({"success": True, "nodes": nodes, "remnawave": True})
        except Exception as e:
            logger.error("Ошибка /api/admin/nodes: %s", e, exc_info=True)
            return jsonify({"error": str(e)}), 500

    @bp.route("/api/admin/node-map-override", methods=["POST", "OPTIONS"])
    def api_admin_node_map_override():
        """Сохранить расположение на карте для ноды Remnawave."""
        if request.method == "OPTIONS":
            return options_response()
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({"error": "Access denied"}), 403
            data = request.get_json(silent=True) or {}
            node_uuid = (data.get("node_uuid") or data.get("uuid") or "").strip()
            if not node_uuid:
                return jsonify({"error": "node_uuid обязателен"}), 400
            lat_val = data.get("lat")
            lng_val = data.get("lng")
            map_label = (data.get("map_label") or "").strip() or None
            if lat_val is None and lng_val is None and map_label is None:
                return jsonify({"error": "Укажите lat, lng или map_label"}), 400
            try:
                lat = float(lat_val) if lat_val is not None else None
                lng = float(lng_val) if lng_val is not None else None
            except (TypeError, ValueError):
                return jsonify({"error": "Некорректные координаты"}), 400
            from .....db import upsert_node_map_override
            _run_async(upsert_node_map_override(node_uuid, lat=lat, lng=lng, map_label=map_label))
            return jsonify({"success": True, "node_uuid": node_uuid})
        except Exception as e:
            logger.error("Ошибка /api/admin/node-map-override: %s", e, exc_info=True)
            return jsonify({"error": str(e)}), 500

