"""Low-level helper functions for xui_service.

Все вспомогательные функции работают с сырым ответом 3x-ui (dict / list / str).
Зависимостей на py3xui-модели больше нет.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Dict, Optional


def client_to_api_dict(c: Any) -> dict:
    """Нормализует словарь клиента 3x-ui к camelCase ключам.

    Принимает:
      - dict от panel API,
      - lightweight-объект (для совместимости с тестами/моками).
    """
    if isinstance(c, dict):
        d = dict(c)
    elif hasattr(c, "model_dump") and callable(getattr(c, "model_dump", None)):
        # Лёгкая совместимость с тестами/моками, у которых есть model_dump().
        maybe_dump = c.model_dump()
        d = maybe_dump if isinstance(maybe_dump, dict) else {}
    else:
        d = {}
        for attr in (
            "email", "id", "uuid", "expiry_time", "expiryTime",
            "limit_ip", "limitIp", "flow", "auth", "password",
            "sub_id", "subId", "tg_id", "tgId", "total_gb", "totalGB",
            "enable",
        ):
            if hasattr(c, attr):
                d[attr] = getattr(c, attr)

    key_map = {
        "expiry_time": "expiryTime",
        "limit_ip": "limitIp",
        "sub_id": "subId",
        "tg_id": "tgId",
        "total_gb": "totalGB",
    }
    out = {key_map.get(k, k): v for k, v in d.items()}
    return out


def clients_from_settings_payload(settings: Dict[str, Any]) -> list[dict]:
    """
    Возвращает плоский список клиентов из 3x-ui settings JSON.

    Часть протоколов (особенно hysteria2) хранит клиентов в `users`,
    а не в `clients`; нормализуем оба варианта в один список.
    """
    rows: list[dict] = []
    for key in ("clients", "users"):
        raw = settings.get(key) or []
        if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes, dict)):
            continue
        for item in raw:
            rows.append(client_to_api_dict(item))
    return rows


def normalize_client_flow_value(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def dedupe_flow_json_key(d: Dict[str, Any]) -> None:
    """Оставляет только lower-case ключ `flow`."""
    for k in list(d.keys()):
        if isinstance(k, str) and k != "flow" and k.lower() == "flow":
            d.pop(k, None)


def panel_client_settings_dict(
    c: Any,
    flow_override: Optional[str] = None,
    protocol_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """Готовит запись `clients[0]` для запросов addClient/updateClient."""
    if isinstance(c, dict):
        d = dict(c)
    elif hasattr(c, "model_dump") and callable(getattr(c, "model_dump", None)):
        d = c.model_dump(by_alias=True, mode="json", exclude_defaults=False)
    else:
        d = {}
    if "expiry_time" in d:
        d["expiryTime"] = d.get("expiry_time")
        d.pop("expiry_time", None)
    if "limit_ip" in d:
        d["limitIp"] = d.get("limit_ip")
        d.pop("limit_ip", None)
    if "sub_id" in d:
        d["subId"] = d.get("sub_id")
        d.pop("sub_id", None)
    if "tg_id" in d:
        d["tgId"] = d.get("tg_id")
        d.pop("tg_id", None)
    dedupe_flow_json_key(d)
    # flow релевантен только для VLESS/XTLS сценариев; для прочих протоколов
    # (например hysteria2/tuic) не добавляем лишние поля.
    protocol = str(protocol_hint or d.get("protocol", "") or "").strip().lower()
    supports_flow = protocol in ("", "vless")
    if flow_override is not None and supports_flow:
        d["flow"] = str(flow_override).strip() if str(flow_override).strip() else ""
    elif supports_flow:
        fv = d.get("flow", None) if isinstance(c, dict) else getattr(c, "flow", None)
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


def _panel_enable_is_disabled(panel_enable: Any) -> bool:
    """Best-effort parse: True если клиент на панели в статусе disabled."""
    if panel_enable is None:
        return False
    if isinstance(panel_enable, bool):
        return panel_enable is False
    if isinstance(panel_enable, (int, float)):
        return int(panel_enable) == 0
    s = str(panel_enable).strip().lower()
    if s in ("false", "0", "off", "no", "disabled"):
        return True
    if s in ("true", "1", "on", "yes", "enabled"):
        return False
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
    """True если снимок клиента из list() соответствует желаемому состоянию."""
    if not panel_snapshot.get("on_panel"):
        return False
    protocol = str(panel_snapshot.get("protocol") or "").strip().lower()
    if protocol in ("hysteria", "hysteria2", "hy2"):
        # У hy2 секрет хранится в `auth`; на старых записях может встречаться `password`.
        # Если оба пусты — строка "битая" и нуждается в reconcile.
        auth_val = str(panel_snapshot.get("auth") or "").strip()
        password_val = str(panel_snapshot.get("password") or "").strip()
        if not (auth_val or password_val):
            return False
    if _panel_enable_is_disabled(panel_snapshot.get("enable")):
        return False
    se = panel_snapshot.get("expiry_sec")
    if not _expiry_sec_matches_panel(se, expiry_sec):
        return False
    if not _limit_ip_matches_panel(panel_snapshot.get("limit_ip"), limit_ip):
        return False
    if not flow_matches_desired(panel_snapshot.get("flow"), flow_from_config):
        return False
    return True
