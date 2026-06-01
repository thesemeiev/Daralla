"""Merge 3x-ui /clash/{subId} YAML into a single Mihomo subscription for FlClash."""

from __future__ import annotations

import logging
import re
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_CLASH_CLIENT_MARKERS = (
    "flclash",
    "fi clash",
    "clash.meta",
    "clash meta",
    "clashmeta",
    "mihomo",
    "clash-verge",
    "clash verge",
    "clashforwindows",
    "stash",
    "surfboard",
)

_PANEL_CLASH_ERROR_MARKERS = ("error!",)


def is_clash_subscription_client(
    user_agent: str,
    x_client: str = "",
    *,
    query: dict[str, str] | None = None,
) -> bool:
    """Detect FlClash / Mihomo / other Clash Meta clients."""
    haystack = f"{user_agent} {x_client}".lower()
    if any(marker in haystack for marker in _CLASH_CLIENT_MARKERS):
        return True
    if not query:
        return False
    fmt = (query.get("format") or query.get("target") or "").strip().lower()
    if fmt in {"clash", "clashmeta", "mihomo", "meta"}:
        return True
    flag = (query.get("clash") or "").strip().lower()
    return flag in {"1", "true", "yes", "on"}


def is_valid_panel_clash_body(text: str) -> bool:
    """Reject 3x-ui error responses and bodies without proxies."""
    raw = (text or "").strip()
    if not raw:
        return False
    lowered = raw.lower()
    if lowered in _PANEL_CLASH_ERROR_MARKERS or lowered.startswith("error"):
        return False
    if "proxies:" not in raw and "proxies" not in raw:
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError:
            return False
        if not isinstance(data, dict) or not data.get("proxies"):
            return False
    return True


def parse_panel_clash_yaml(text: str) -> list[dict[str, Any]]:
    """Extract proxy list from panel Clash YAML (ignore panel proxy-groups/rules)."""
    raw = (text or "").strip()
    if not raw:
        return []
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError:
        logger.debug("parse_panel_clash_yaml: YAML parse failed", exc_info=True)
        return []
    if not isinstance(data, dict):
        return []
    proxies = data.get("proxies")
    if not isinstance(proxies, list):
        return []
    out: list[dict[str, Any]] = []
    for item in proxies:
        if isinstance(item, dict) and item.get("name"):
            out.append(dict(item))
    return out


def merge_panel_clash_proxies(proxy_lists: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Merge proxies from multiple panels; dedupe by name with numeric suffix."""
    merged: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for proxies in proxy_lists:
        for proxy in proxies:
            name = str(proxy.get("name") or "").strip()
            if not name:
                continue
            base_name = name
            suffix = 2
            while name in seen_names:
                name = f"{base_name}-{suffix}"
                suffix += 1
            entry = dict(proxy)
            entry["name"] = name
            seen_names.add(name)
            merged.append(entry)
    return merged


def _yaml_quote(value: str) -> str:
    if value == "":
        return '""'
    if re.fullmatch(r"[A-Za-z0-9_./:-]+", value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _emit_yaml(value: Any, indent: int = 0) -> str:
    pad = "  " * indent
    if isinstance(value, dict):
        if not value:
            return "{}"
        lines: list[str] = []
        for key, item in value.items():
            rendered = _emit_yaml(item, indent + 1)
            if isinstance(item, (dict, list)) and item:
                lines.append(f"{pad}{key}:")
                lines.append(rendered)
            else:
                lines.append(f"{pad}{key}: {rendered}")
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return f"{pad}[]"
        lines = []
        for item in value:
            if isinstance(item, dict):
                lines.append(f"{pad}-")
                block = _emit_yaml(item, indent + 1)
                lines.append(block)
            else:
                lines.append(f"{pad}- {_emit_yaml(item, 0)}")
        return "\n".join(lines)
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    return _yaml_quote(str(value))


def build_merged_clash_config(proxies: list[dict[str, Any]], *, group_name: str) -> dict[str, Any]:
    """Daralla-owned Mihomo shell (proxy-groups, rules) around merged panel proxies."""
    clean_group = (group_name or "Daralla VPN").strip() or "Daralla VPN"
    proxy_names = [str(p["name"]) for p in proxies if p.get("name")]

    select_proxies: list[str] = []
    if proxy_names:
        select_proxies.extend(["AUTO", *proxy_names, "DIRECT"])
    else:
        select_proxies.append("DIRECT")

    proxy_groups: list[dict[str, Any]] = [
        {
            "name": clean_group,
            "type": "select",
            "proxies": select_proxies,
        },
    ]
    if proxy_names:
        proxy_groups.append(
            {
                "name": "AUTO",
                "type": "url-test",
                "proxies": proxy_names,
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
                "tolerance": 50,
            }
        )

    return {
        "mixed-port": 7890,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "info",
        "proxies": proxies,
        "proxy-groups": proxy_groups,
        "rules": [f"MATCH,{clean_group}"],
    }


def build_clash_subscription_from_panels(
    panel_bodies: list[str],
    *,
    group_name: str,
) -> str:
    """Parse panel YAML bodies, merge proxies, emit final subscription YAML."""
    proxy_lists = [parse_panel_clash_yaml(body) for body in panel_bodies]
    proxies = merge_panel_clash_proxies(proxy_lists)
    return render_clash_subscription_yaml(proxies, group_name=group_name)


def render_clash_subscription_yaml(
    proxies: list[dict[str, Any]],
    *,
    group_name: str,
) -> str:
    """Render full subscription document (used for empty inactive subs too)."""
    clean_group = (group_name or "Daralla VPN").strip() or "Daralla VPN"
    config = build_merged_clash_config(proxies, group_name=clean_group)
    header = (
        "# Clash Meta / Mihomo subscription\n"
        f"# profile-title: {clean_group}\n"
    )
    return header + _emit_yaml(config) + "\n"


def clash_subscription_headers_overrides() -> dict[str, str]:
    return {
        "Content-Type": "application/yaml; charset=utf-8",
    }
