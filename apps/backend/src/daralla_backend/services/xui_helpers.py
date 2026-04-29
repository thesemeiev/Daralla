"""Low-level helper functions for xui_service."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any, Dict, Optional


def client_to_api_dict(c: Any) -> dict:
    """Convert py3xui client (or dict) to 3x-ui API dict (camelCase keys)."""
    if hasattr(c, "model_dump"):
        d = c.model_dump()
    elif isinstance(c, dict):
        d = dict(c)
    else:
        d = {}
    key_map = {
        "expiry_time": "expiryTime",
        "limit_ip": "limitIp",
        "sub_id": "subId",
        "tg_id": "tgId",
        "total_gb": "totalGB",
    }
    out = {}
    for k, v in d.items():
        out[key_map.get(k, k)] = v
    if not isinstance(c, dict) and hasattr(c, "flow"):
        raw = getattr(c, "flow", None)
        out["flow"] = "" if raw is None else str(raw).strip()
    return out


def clients_from_settings_payload(settings: Dict[str, Any]) -> list[dict]:
    """
    Return unified client rows from 3x-ui settings JSON.

    Some protocols/panel versions store users under ``users`` instead of ``clients``
    (notably hysteria2). We normalize both into one list.
    """
    rows: list[dict] = []
    for key in ("clients", "users"):
        raw = settings.get(key) or []
        if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes, dict)):
            continue
        for item in raw:
            if isinstance(item, dict):
                rows.append(client_to_api_dict(item))
            else:
                rows.append(client_to_api_dict(item))
    return rows


def normalize_client_flow_value(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def dedupe_flow_json_key(d: Dict[str, Any]) -> None:
    """Keep only lower-case flow key."""
    for k in list(d.keys()):
        if isinstance(k, str) and k != "flow" and k.lower() == "flow":
            d.pop(k, None)


def panel_client_settings_dict(
    c: Any,
    flow_override: Optional[str] = None,
    protocol_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """Build clients[] payload for addClient/updateClient."""
    if isinstance(c, dict):
        d = dict(c)
    elif hasattr(c, "model_dump"):
        d = c.model_dump(by_alias=True, mode="json", exclude_defaults=False)
    else:
        d = {}
    dedupe_flow_json_key(d)
    # flow релевантен только для VLESS/XTLS сценариев; для прочих протоколов
    # (например hysteria2/tuic) не добавляем лишние поля.
    protocol = str(protocol_hint or d.get("protocol", "") or "").strip().lower()
    supports_flow = protocol in ("", "vless")
    if flow_override is not None and supports_flow:
        d["flow"] = str(flow_override).strip() if str(flow_override).strip() else ""
    elif supports_flow:
        fv = getattr(c, "flow", None)
        d["flow"] = "" if fv is None else str(fv).strip()
    else:
        d.pop("flow", None)
    return d


def _expiry_sec_matches_panel(panel_sec: Optional[int], db_sec: int, tolerance_sec: int = 300) -> bool:
    if panel_sec is None:
        return False
    return abs(int(panel_sec) - int(db_sec)) <= tolerance_sec


def _limit_ip_matches_panel(panel_limit: Any, device_limit: int) -> bool:
    if panel_limit is None or panel_limit == 0:
        return False
    try:
        return int(panel_limit) == int(device_limit)
    except (TypeError, ValueError):
        return False


def flow_matches_desired(panel_flow: Any, flow_from_config: Optional[str]) -> bool:
    desired = (flow_from_config or "").strip()
    panel = normalize_client_flow_value(panel_flow)
    return desired == panel


def panel_snapshot_matches_desired(
    panel_snapshot: dict,
    expiry_sec: int,
    limit_ip: int,
    flow_from_config: Optional[str],
) -> bool:
    """True if panel list() snapshot matches desired state."""
    if not panel_snapshot.get("on_panel"):
        return False
    se = panel_snapshot.get("expiry_sec")
    if not _expiry_sec_matches_panel(se, expiry_sec):
        return False
    if not _limit_ip_matches_panel(panel_snapshot.get("limit_ip"), limit_ip):
        return False
    if not flow_matches_desired(panel_snapshot.get("flow"), flow_from_config):
        return False
    return True


def inbound_to_dict(inv: Any) -> dict:
    """Convert py3xui Inbound object to list() payload entry."""
    settings = getattr(inv, "settings", None)
    clients = []
    if settings is not None:
        raw_clients = (getattr(settings, "clients", None) or []) + (getattr(settings, "users", None) or [])
        for c in raw_clients:
            clients.append(client_to_api_dict(c))
    settings_str = json.dumps({"clients": clients})

    stream = getattr(inv, "stream_settings", None)
    if stream is not None and hasattr(stream, "model_dump"):
        stream_dict = stream.model_dump()
    elif isinstance(stream, dict):
        stream_dict = stream
    else:
        stream_dict = {}

    client_stats = getattr(inv, "client_stats", None) or []
    client_stats_list = []
    for s in client_stats:
        if hasattr(s, "model_dump"):
            client_stats_list.append(s.model_dump())
        elif isinstance(s, dict):
            client_stats_list.append(s)
        else:
            client_stats_list.append(client_to_api_dict(s))

    return {
        "id": getattr(inv, "id", None),
        "protocol": getattr(inv, "protocol", "vless"),
        "port": getattr(inv, "port", 443),
        "settings": settings_str,
        "streamSettings": stream_dict,
        "clientStats": client_stats_list if client_stats_list else [],
        "enable": getattr(inv, "enable", True),
        "remark": getattr(inv, "remark", ""),
    }
