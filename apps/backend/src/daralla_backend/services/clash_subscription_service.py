"""Convert V2Ray-style subscription links to Clash Meta (Mihomo) YAML for FlClash."""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

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

_URI_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


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


def _first(params: dict[str, list[str]], key: str, default: str = "") -> str:
    values = params.get(key)
    if not values:
        return default
    return str(values[0]).strip()


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


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


def _proxy_name_from_uri(uri: str, fallback: str) -> str:
    if "#" in uri:
        name = unquote(uri.rsplit("#", 1)[1]).strip()
        if name:
            return name
    return fallback


def _vless_uri_to_proxy(uri: str, fallback_name: str) -> dict[str, Any] | None:
    parsed = urlparse(uri)
    if parsed.scheme != "vless":
        return None
    userinfo = parsed.username or ""
    uuid = unquote(userinfo) if userinfo else ""
    host = parsed.hostname or ""
    port = parsed.port or 443
    params = parse_qs(parsed.query, keep_blank_values=True)
    name = _proxy_name_from_uri(uri, fallback_name)

    proxy: dict[str, Any] = {
        "name": name,
        "type": "vless",
        "server": host,
        "port": int(port),
        "uuid": uuid,
        "udp": True,
    }

    network = _first(params, "type", "tcp") or "tcp"
    if network:
        proxy["network"] = network

    flow = _first(params, "flow")
    if flow:
        proxy["flow"] = flow

    security = _first(params, "security", "none").lower()
    sni = _first(params, "sni") or _first(params, "host")
    fp = _first(params, "fp") or _first(params, "fingerprint")

    if security in {"reality", "tls"}:
        proxy["tls"] = True
    if sni:
        proxy["servername"] = sni
    if fp:
        proxy["client-fingerprint"] = fp
    if _truthy(_first(params, "allowInsecure")) or _truthy(_first(params, "insecure")):
        proxy["skip-cert-verify"] = True

    alpn = _first(params, "alpn")
    if alpn:
        proxy["alpn"] = [part.strip() for part in alpn.split(",") if part.strip()]

    if security == "reality":
        public_key = _first(params, "pbk") or _first(params, "publicKey")
        short_id = _first(params, "sid") or _first(params, "shortId")
        reality_opts: dict[str, str] = {}
        if public_key:
            reality_opts["public-key"] = public_key
        if short_id:
            reality_opts["short-id"] = short_id
        if reality_opts:
            proxy["reality-opts"] = reality_opts

    if network == "ws":
        ws_opts: dict[str, Any] = {}
        path = _first(params, "path", "/") or "/"
        ws_opts["path"] = path
        ws_host = _first(params, "host")
        if ws_host:
            ws_opts["headers"] = {"Host": ws_host}
        proxy["ws-opts"] = ws_opts
    elif network == "grpc":
        service_name = _first(params, "serviceName") or _first(params, "serviceName")
        if service_name:
            proxy["grpc-opts"] = {"grpc-service-name": service_name}
    elif network in {"http", "h2"}:
        http_opts: dict[str, Any] = {}
        path = _first(params, "path")
        if path:
            http_opts["path"] = [path]
        http_host = _first(params, "host")
        if http_host:
            http_opts["headers"] = {"Host": [http_host]}
        if http_opts:
            proxy["http-opts"] = http_opts

    packet_encoding = _first(params, "packetEncoding")
    if packet_encoding:
        proxy["packet-encoding"] = packet_encoding

    return proxy


def _trojan_uri_to_proxy(uri: str, fallback_name: str) -> dict[str, Any] | None:
    parsed = urlparse(uri)
    if parsed.scheme != "trojan":
        return None
    password = unquote(parsed.username or "")
    host = parsed.hostname or ""
    port = parsed.port or 443
    params = parse_qs(parsed.query, keep_blank_values=True)
    name = _proxy_name_from_uri(uri, fallback_name)

    proxy: dict[str, Any] = {
        "name": name,
        "type": "trojan",
        "server": host,
        "port": int(port),
        "password": password,
        "udp": True,
    }
    sni = _first(params, "sni") or _first(params, "peer")
    if sni:
        proxy["sni"] = sni
    fp = _first(params, "fp")
    if fp:
        proxy["client-fingerprint"] = fp
    if _truthy(_first(params, "allowInsecure")):
        proxy["skip-cert-verify"] = True
    alpn = _first(params, "alpn")
    if alpn:
        proxy["alpn"] = [part.strip() for part in alpn.split(",") if part.strip()]
    network = _first(params, "type")
    if network == "ws":
        ws_opts: dict[str, Any] = {"path": _first(params, "path", "/") or "/"}
        ws_host = _first(params, "host")
        if ws_host:
            ws_opts["headers"] = {"Host": ws_host}
        proxy["network"] = "ws"
        proxy["ws-opts"] = ws_opts
    return proxy


def _vmess_uri_to_proxy(uri: str, fallback_name: str) -> dict[str, Any] | None:
    if not uri.startswith("vmess://"):
        return None
    payload = uri[len("vmess://") :]
    if "?" in payload:
        payload = payload.split("?", 1)[0]
    padding = "=" * (-len(payload) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload + padding).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        try:
            data = json.loads(base64.standard_b64decode(payload + padding).decode("utf-8"))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("vmess URI decode failed")
            return None

    name = _proxy_name_from_uri(uri, fallback_name) or str(data.get("ps") or fallback_name)
    proxy: dict[str, Any] = {
        "name": name,
        "type": "vmess",
        "server": str(data.get("add") or ""),
        "port": int(data.get("port") or 443),
        "uuid": str(data.get("id") or ""),
        "alterId": int(data.get("aid") or 0),
        "cipher": "auto",
        "udp": True,
    }
    if data.get("tls") == "tls":
        proxy["tls"] = True
    if data.get("sni") or data.get("host"):
        proxy["servername"] = str(data.get("sni") or data.get("host"))
    network = str(data.get("net") or "tcp")
    if network:
        proxy["network"] = network
    if network == "ws":
        ws_opts: dict[str, Any] = {"path": str(data.get("path") or "/")}
        host_header = data.get("host")
        if host_header:
            ws_opts["headers"] = {"Host": str(host_header)}
        proxy["ws-opts"] = ws_opts
    return proxy


def _hysteria2_uri_to_proxy(uri: str, fallback_name: str) -> dict[str, Any] | None:
    parsed = urlparse(uri)
    if parsed.scheme not in {"hysteria2", "hy2"}:
        return None
    password = unquote(parsed.username or "")
    host = parsed.hostname or ""
    port = parsed.port or 443
    params = parse_qs(parsed.query, keep_blank_values=True)
    name = _proxy_name_from_uri(uri, fallback_name)
    proxy: dict[str, Any] = {
        "name": name,
        "type": "hysteria2",
        "server": host,
        "port": int(port),
        "password": password,
        "udp": True,
    }
    sni = _first(params, "sni")
    if sni:
        proxy["sni"] = sni
    alpn = _first(params, "alpn")
    if alpn:
        proxy["alpn"] = [part.strip() for part in alpn.split(",") if part.strip()]
    if _truthy(_first(params, "insecure")):
        proxy["skip-cert-verify"] = True
    obfs = _first(params, "obfs")
    obfs_password = _first(params, "obfs-password")
    if obfs:
        proxy["obfs"] = obfs
    if obfs_password:
        proxy["obfs-password"] = obfs_password
    return proxy


def _tuic_uri_to_proxy(uri: str, fallback_name: str) -> dict[str, Any] | None:
    parsed = urlparse(uri)
    if parsed.scheme != "tuic":
        return None
    uuid = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    host = parsed.hostname or ""
    port = parsed.port or 443
    params = parse_qs(parsed.query, keep_blank_values=True)
    name = _proxy_name_from_uri(uri, fallback_name)
    proxy: dict[str, Any] = {
        "name": name,
        "type": "tuic",
        "server": host,
        "port": int(port),
        "uuid": uuid,
        "password": password,
        "udp": True,
    }
    sni = _first(params, "sni")
    if sni:
        proxy["sni"] = sni
    cc = _first(params, "congestion_control") or _first(params, "congestion-control")
    if cc:
        proxy["congestion-controller"] = cc
    alpn = _first(params, "alpn")
    if alpn:
        proxy["alpn"] = [part.strip() for part in alpn.split(",") if part.strip()]
    if _truthy(_first(params, "allowInsecure")):
        proxy["skip-cert-verify"] = True
    return proxy


def uri_to_clash_proxy(uri: str, *, fallback_name: str = "node") -> dict[str, Any] | None:
    uri = (uri or "").strip()
    if not uri or not _URI_SCHEME_RE.match(uri):
        return None
    scheme = uri.split(":", 1)[0].lower()
    converters = {
        "vless": _vless_uri_to_proxy,
        "trojan": _trojan_uri_to_proxy,
        "vmess": _vmess_uri_to_proxy,
        "hysteria2": _hysteria2_uri_to_proxy,
        "hy2": _hysteria2_uri_to_proxy,
        "tuic": _tuic_uri_to_proxy,
    }
    converter = converters.get(scheme)
    if not converter:
        logger.debug("Clash export: unsupported scheme %s", scheme)
        return None
    return converter(uri, fallback_name)


def build_clash_subscription_yaml(links: list[str], *, group_name: str) -> str:
    """Build Mihomo-compatible YAML subscription from share links."""
    proxies: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for index, link in enumerate(links, start=1):
        proxy = uri_to_clash_proxy(link, fallback_name=f"node-{index}")
        if not proxy:
            continue
        name = str(proxy.get("name") or f"node-{index}")
        base_name = name
        suffix = 2
        while name in seen_names:
            name = f"{base_name}-{suffix}"
            suffix += 1
        proxy["name"] = name
        seen_names.add(name)
        proxies.append(proxy)

    clean_group = (group_name or "Daralla VPN").strip() or "Daralla VPN"
    proxy_names = [str(p["name"]) for p in proxies]

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

    config: dict[str, Any] = {
        "mixed-port": 7890,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "info",
        "proxies": proxies,
        "proxy-groups": proxy_groups,
        "rules": [f"MATCH,{clean_group}"],
    }

    header = (
        "# Clash Meta / Mihomo subscription\n"
        f"# profile-title: {clean_group}\n"
    )
    return header + _emit_yaml(config) + "\n"


def clash_subscription_headers_overrides() -> dict[str, str]:
    return {
        "Content-Type": "application/yaml; charset=utf-8",
    }
