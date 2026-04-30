"""Helper functions extracted from subscription manager."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, Dict, Optional

from .xui_helpers import clients_from_settings_payload


logger = logging.getLogger(__name__)
_PROTOCOL_PREFIXES = ("vless://", "trojan://", "vmess://", "ss://", "socks://")


def clients_by_email_from_xui_list_response(list_payload: dict) -> Dict[str, Dict[str, Any]]:
    """
    Build map from xui.list() snapshot: email -> panel attributes.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for inbound in list_payload.get("obj") or []:
        protocol = (inbound.get("protocol") or "vless").lower()
        try:
            settings = json.loads(inbound.get("settings") or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        for client in clients_from_settings_payload(settings):
            email = client.get("email")
            if not email:
                continue
            email = str(email)
            if email in out:
                logger.warning(
                    "X-UI list snapshot: email %s duplicated across inbounds, keeping last protocol=%s",
                    email,
                    protocol,
                )
            expiry_ms = client.get("expiryTime") or 0
            expiry_sec = None if not expiry_ms or int(expiry_ms) <= 0 else int(expiry_ms) // 1000
            flow_raw = client.get("flow")
            if flow_raw is None:
                flow_raw = client.get("Flow")
            flow_s = (str(flow_raw).strip() if flow_raw is not None else "") or ""
            out[email] = {
                "expiry_sec": expiry_sec,
                "limit_ip": client.get("limitIp"),
                "flow": flow_s,
                "enable": client.get("enable"),
                "protocol": protocol,
                "auth": client.get("auth"),
                "password": client.get("password"),
            }
    return out


def panel_entry_from_snapshot(
    email_map: Optional[Dict[str, Dict[str, Any]]], client_email: str
) -> Optional[dict]:
    """Return normalized panel snapshot row for ensure_client_on_server."""
    if email_map is None:
        return None
    row = email_map.get(client_email)
    if row is None:
        return {"on_panel": False}
    return {
        "on_panel": True,
        "expiry_sec": row["expiry_sec"],
        "limit_ip": row.get("limit_ip"),
        "flow": row.get("flow"),
        "enable": row.get("enable"),
        "protocol": row.get("protocol") or "vless",
        "auth": row.get("auth"),
        "password": row.get("password"),
    }


def normalize_subscription_link(link: str) -> str:
    """Decode base64 encoded subscription links when needed."""
    if not link or not link.strip():
        return link
    s = link.strip()
    if s.startswith(_PROTOCOL_PREFIXES):
        return s
    try:
        raw = base64.b64decode(s)
        decoded = raw.decode("utf-8")
        if decoded.startswith(_PROTOCOL_PREFIXES):
            return decoded
    except (ValueError, TypeError):
        pass
    return s
