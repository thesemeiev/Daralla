"""
Единый источник тарифов и цен на подписки.

Поддерживает:
- legacy-ключи (price_month, price_3month) для совместимости;
- расширяемый список тарифов в config (tariffs_json_v1).
"""
import copy
import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

_ENV_MONTH = int(os.getenv("PRICE_MONTH", "150"))
_ENV_3MONTH = int(os.getenv("PRICE_3MONTH", "350"))

PRICE_MONTH = _ENV_MONTH
PRICE_3MONTH = _ENV_3MONTH

PRICES = {
    "month": PRICE_MONTH,
    "3month": PRICE_3MONTH,
}

DEFAULT_TARIFFS = [
    {"period": "month", "title": "1 месяц", "days": 30, "price": _ENV_MONTH, "badge": ""},
    {"period": "3month", "title": "3 месяца", "days": 90, "price": _ENV_3MONTH, "badge": "best"},
]
TARIFFS: list[dict[str, Any]] = copy.deepcopy(DEFAULT_TARIFFS)

CONFIG_KEY_PRICE_MONTH = "price_month"
CONFIG_KEY_PRICE_3MONTH = "price_3month"
CONFIG_KEY_DEFAULT_DEVICE_LIMIT = "default_device_limit"
CONFIG_KEY_TARIFFS_JSON = "tariffs_json_v1"
CONFIG_KEY_TRAFFIC_TOPUP_JSON = "traffic_topup_packages_json_v1"

ALLOWED_BADGES = {"", "best", "hit"}

_TRAFFIC_TOPUP_ID_RE = re.compile(r"^[a-z0-9_-]{2,40}$")

TRAFFIC_TOPUP_PACKAGES: list[dict[str, Any]] = []


def _clamp_price(value: int) -> int:
    return max(1, min(int(value), 2_000_000))


def _clamp_days(value: int) -> int:
    return max(1, min(int(value), 3650))


def _parse_price(raw: str | None, fallback: int) -> int:
    if raw is None or str(raw).strip() == "":
        return _clamp_price(fallback)
    try:
        return _clamp_price(int(float(str(raw).strip().replace(",", "."))))
    except (ValueError, TypeError):
        return _clamp_price(fallback)


def _normalize_tariff_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    period = str(item.get("period") or "").strip().lower()
    if not period:
        return None
    title_raw = str(item.get("title") or "").strip()
    title = title_raw if title_raw else period
    try:
        days = _clamp_days(int(float(str(item.get("days", 30)).strip())))
    except (TypeError, ValueError):
        days = 30
    try:
        price = _clamp_price(int(float(str(item.get("price", 1)).strip().replace(",", "."))))
    except (TypeError, ValueError):
        price = 1
    badge = str(item.get("badge") or "").strip().lower()
    if badge not in ALLOWED_BADGES:
        badge = ""
    return {
        "period": period,
        "title": title[:60],
        "days": days,
        "price": price,
        "badge": badge,
    }


def _clamp_gib(value: float) -> float:
    return max(0.001, min(float(value), 4096.0))


def _normalize_traffic_topup_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    pid = str(item.get("id") or "").strip().lower()
    if not pid or not _TRAFFIC_TOPUP_ID_RE.match(pid):
        return None
    title_raw = str(item.get("title") or "").strip()
    title = title_raw if title_raw else pid
    try:
        gib = _clamp_gib(float(str(item.get("gib", 0)).replace(",", ".")))
    except (TypeError, ValueError):
        return None
    try:
        price = _clamp_price(int(float(str(item.get("price", 1)).strip().replace(",", "."))))
    except (TypeError, ValueError):
        price = 1
    badge = str(item.get("badge") or "").strip().lower()
    if badge not in ALLOWED_BADGES:
        badge = ""
    en = item.get("enabled", True)
    if isinstance(en, str):
        enabled = en.strip().lower() not in ("0", "false", "no", "")
    else:
        enabled = bool(en)
    try:
        sort_order = int(item.get("sort_order", 0))
    except (TypeError, ValueError):
        sort_order = 0
    bytes_total = int(round(gib * (1024**3)))
    if bytes_total < 1:
        return None
    return {
        "id": pid,
        "title": title[:80],
        "gib": round(gib, 6),
        "bytes_total": bytes_total,
        "price": price,
        "badge": badge,
        "enabled": enabled,
        "sort_order": sort_order,
    }


def normalize_traffic_topup_packages(raw_items: Any) -> list[dict[str, Any]]:
    items = raw_items if isinstance(raw_items, list) else []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        norm = _normalize_traffic_topup_item(item)
        if not norm:
            continue
        iid = norm["id"]
        if iid in seen:
            continue
        seen.add(iid)
        out.append(norm)
    out.sort(key=lambda x: (int(x.get("sort_order", 0)), str(x.get("id"))))
    return out


def get_traffic_topup_packages() -> list[dict[str, Any]]:
    return copy.deepcopy(TRAFFIC_TOPUP_PACKAGES)


def get_public_traffic_topup_packages() -> list[dict[str, Any]]:
    """Каталог для пользовательского UI (без служебных полей)."""
    pub = []
    for p in TRAFFIC_TOPUP_PACKAGES:
        if not p.get("enabled", True):
            continue
        pub.append(
            {
                "id": p["id"],
                "title": p["title"],
                "gib": p["gib"],
                "price": int(p["price"]),
                "badge": p.get("badge") or "",
            }
        )
    return pub


def get_traffic_topup_package(package_id: str | None) -> dict[str, Any] | None:
    key = str(package_id or "").strip().lower()
    if not key:
        return None
    for p in TRAFFIC_TOPUP_PACKAGES:
        if p.get("id") == key and p.get("enabled", True):
            return dict(p)
    return None


def normalize_tariffs(raw_items: Any) -> list[dict[str, Any]]:
    items = raw_items if isinstance(raw_items, list) else []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        norm = _normalize_tariff_item(item)
        if not norm:
            continue
        period = norm["period"]
        if period in seen:
            continue
        seen.add(period)
        out.append(norm)
    out.sort(key=lambda x: (int(x.get("days", 0)), str(x.get("period"))))
    return out


def get_tariffs() -> list[dict[str, Any]]:
    return copy.deepcopy(TARIFFS)


def get_tariff(period: str | None) -> dict[str, Any] | None:
    key = str(period or "").strip().lower()
    if not key:
        return None
    for tariff in TARIFFS:
        if tariff.get("period") == key:
            return dict(tariff)
    return None


def get_tariff_days(period: str | None, default_days: int = 30) -> int:
    tariff = get_tariff(period)
    if not tariff:
        return default_days
    try:
        return _clamp_days(int(tariff.get("days", default_days)))
    except (TypeError, ValueError):
        return default_days


async def refresh_prices_from_db() -> None:
    """Обновляет тарифы и словарь PRICES из БД (или env по умолчанию)."""
    global PRICE_MONTH, PRICE_3MONTH, TARIFFS
    from daralla_backend.db.config_db import get_config

    tariffs_raw = await get_config(CONFIG_KEY_TARIFFS_JSON, None)
    tariffs: list[dict[str, Any]] = []
    if tariffs_raw:
        try:
            parsed = json.loads(tariffs_raw)
            tariffs = normalize_tariffs(parsed)
        except Exception:
            tariffs = []

    if not tariffs:
        # Backward compatibility: собираем базовые два тарифа из старых ключей.
        pm = await get_config(CONFIG_KEY_PRICE_MONTH, None)
        p3 = await get_config(CONFIG_KEY_PRICE_3MONTH, None)
        month_price = _parse_price(pm, _ENV_MONTH)
        three_price = _parse_price(p3, _ENV_3MONTH)
        tariffs = [
            {"period": "month", "title": "1 месяц", "days": 30, "price": month_price, "badge": ""},
            {"period": "3month", "title": "3 месяца", "days": 90, "price": three_price, "badge": "best"},
        ]

    TARIFFS = normalize_tariffs(tariffs) or copy.deepcopy(DEFAULT_TARIFFS)

    PRICES.clear()
    for tariff in TARIFFS:
        PRICES[str(tariff["period"])] = int(tariff["price"])

    PRICE_MONTH = int(PRICES.get("month", _ENV_MONTH))
    PRICE_3MONTH = int(PRICES.get("3month", _ENV_3MONTH))
    logger.debug("Тарифы в памяти: %s", TARIFFS)

    await refresh_traffic_topup_packages_from_db()


async def refresh_traffic_topup_packages_from_db() -> None:
    """Загружает пакеты докупки трафика из config (может быть пустой список)."""
    global TRAFFIC_TOPUP_PACKAGES
    from daralla_backend.db.config_db import get_config

    raw = await get_config(CONFIG_KEY_TRAFFIC_TOPUP_JSON, None)
    packages: list[dict[str, Any]] = []
    if raw:
        try:
            parsed = json.loads(raw)
            packages = normalize_traffic_topup_packages(parsed)
        except Exception:
            packages = []
    TRAFFIC_TOPUP_PACKAGES = packages


async def get_default_device_limit_async() -> int:
    """Лимит устройств (limitIp) для новых оплат и пробной подписки по умолчанию."""
    from daralla_backend.db.config_db import get_config

    raw = await get_config(CONFIG_KEY_DEFAULT_DEVICE_LIMIT, "1")
    try:
        return max(1, min(int(float(str(raw).strip())), 100))
    except (ValueError, TypeError):
        return 1
