"""
Сервис для отображения нод Remnawave на карте и в списке.
Объединяет данные Remnawave API с переопределениями координат из БД.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def get_remnawave_nodes_for_display() -> list[dict[str, Any]]:
    """
    Возвращает ноды Remnawave в формате для карты и списка.
    Применяет переопределения координат из node_map_overrides.
    Возвращает [] если Remnawave не настроен или ошибка.
    """
    try:
        from .remnawave_service import is_remnawave_configured, load_remnawave_config, RemnawaveClient
        from ..db import get_node_map_overrides
        from ..utils.country_coords import get_coords_for_country
    except ImportError as e:
        logger.warning("nodes_display: import error %s", e)
        return []

    if not is_remnawave_configured():
        return []

    try:
        cfg = load_remnawave_config()
        client = RemnawaveClient(cfg)
        raw_nodes = await client.get_nodes_async()
    except Exception as e:
        logger.error("nodes_display: failed to fetch Remnawave nodes: %s", e)
        return []

    try:
        overrides = await get_node_map_overrides()
    except Exception as e:
        logger.warning("nodes_display: failed to load overrides: %s", e)
        overrides = {}

    result = []
    for n in raw_nodes:
        uuid_val = n.get("uuid") or n.get("id")
        node_uuid = str(uuid_val) if uuid_val else ""
        name = (n.get("name") or "").strip() or "Node"
        country_code = (n.get("countryCode") or n.get("country_code") or "").strip().upper() or "XX"
        is_connected = n.get("isConnected", n.get("is_connected", False))
        is_disabled = n.get("isDisabled", n.get("is_disabled", False))
        traffic_used = float(n.get("trafficUsedBytes") or n.get("traffic_used_bytes") or 0)
        traffic_limit = float(n.get("trafficLimitBytes") or n.get("traffic_limit_bytes") or 0)

        override = overrides.get(node_uuid, {})
        lat = override.get("lat")
        lng = override.get("lng")
        if lat is None or lng is None:
            lat, lng = get_coords_for_country(country_code)

        map_label = override.get("map_label") or name
        display_name = map_label

        if is_disabled:
            status = "offline"
        elif is_connected:
            status = "online"
        else:
            status = "offline"

        usage_percentage = 0.0
        if traffic_limit > 0 and traffic_used > 0:
            usage_percentage = min(100.0, 100.0 * traffic_used / traffic_limit)

        result.append({
            "uuid": node_uuid,
            "name": name,
            "display_name": display_name,
            "map_label": map_label,
            "location": country_code,
            "lat": lat,
            "lng": lng,
            "usage_count": int(n.get("usersOnline", n.get("users_online")) or 0),
            "usage_percentage": usage_percentage,
            "status": status,
            "address": n.get("address", ""),
            "country_code": country_code,
        })

    return result
