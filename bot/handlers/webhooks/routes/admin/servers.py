"""
Маршруты: ноды Remnawave на карте — список и настройка расположения.
"""
import logging

from flask import request

from ...webhook_utils import APIResponse, require_admin, handle_options, run_async, AuthContext

logger = logging.getLogger(__name__)


def register_servers_routes(bp):
    @bp.route("/api/admin/nodes", methods=["GET", "OPTIONS"])
    @require_admin
    def api_admin_nodes(auth: AuthContext):
        """Список нод Remnawave (с координатами и переопределениями)."""
        if request.method == "OPTIONS":
            return handle_options()
        
        async def fetch():
            from .....services.remnawave_service import is_remnawave_configured
            from .....services.nodes_display_service import get_remnawave_nodes_for_display

            if not is_remnawave_configured():
                return APIResponse.success(nodes=[], remnawave=False)
            
            nodes = await get_remnawave_nodes_for_display()
            return APIResponse.success(nodes=nodes, remnawave=True)
        
        try:
            return run_async(fetch())
        except Exception as e:
            logger.error("Ошибка /api/admin/nodes: %s", e, exc_info=True)
            return APIResponse.internal_error()

    @bp.route("/api/admin/node-map-override", methods=["POST", "OPTIONS"])
    @require_admin
    def api_admin_node_map_override(auth: AuthContext):
        """Сохранить расположение на карте для ноды Remnawave."""
        if request.method == "OPTIONS":
            return handle_options()
        
        data = request.get_json(silent=True) or {}
        node_uuid = (data.get("node_uuid") or data.get("uuid") or "").strip()
        if not node_uuid:
            return APIResponse.bad_request('node_uuid обязателен')
        
        lat_val = data.get("lat")
        lng_val = data.get("lng")
        map_label = (data.get("map_label") or "").strip() or None
        
        if lat_val is None and lng_val is None and map_label is None:
            return APIResponse.bad_request('Укажите lat, lng или map_label')
        
        try:
            lat = float(lat_val) if lat_val is not None else None
            lng = float(lng_val) if lng_val is not None else None
        except (TypeError, ValueError):
            return APIResponse.bad_request('Некорректные координаты')
        
        async def save():
            from .....db import upsert_node_map_override
            await upsert_node_map_override(node_uuid, lat=lat, lng=lng, map_label=map_label)
            return APIResponse.success(node_uuid=node_uuid)
        
        try:
            return run_async(save())
        except Exception as e:
            logger.error("Ошибка /api/admin/node-map-override: %s", e, exc_info=True)
            return APIResponse.internal_error()

