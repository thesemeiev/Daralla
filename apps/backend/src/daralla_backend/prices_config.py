"""
Единый источник цен на подписки.
Базовые значения — из .env (PRICE_MONTH, PRICE_3MONTH); при наличии записей в таблице config
переопределяются через refresh_prices_from_db() (старт приложения и сохранение в админке).
"""
import os
import logging

logger = logging.getLogger(__name__)

_ENV_MONTH = int(os.getenv("PRICE_MONTH", "150"))
_ENV_3MONTH = int(os.getenv("PRICE_3MONTH", "350"))

PRICE_MONTH = _ENV_MONTH
PRICE_3MONTH = _ENV_3MONTH

PRICES = {
    "month": PRICE_MONTH,
    "3month": PRICE_3MONTH,
}

CONFIG_KEY_PRICE_MONTH = "price_month"
CONFIG_KEY_PRICE_3MONTH = "price_3month"
CONFIG_KEY_DEFAULT_DEVICE_LIMIT = "default_device_limit"


def _clamp_price(value: int) -> int:
    return max(1, min(int(value), 2_000_000))


def _parse_price(raw: str | None, fallback: int) -> int:
    if raw is None or str(raw).strip() == "":
        return _clamp_price(fallback)
    try:
        return _clamp_price(int(float(str(raw).strip().replace(",", "."))))
    except (ValueError, TypeError):
        return _clamp_price(fallback)


async def refresh_prices_from_db() -> None:
    """Обновляет PRICE_MONTH, PRICE_3MONTH и словарь PRICES из БД (или env по умолчанию)."""
    global PRICE_MONTH, PRICE_3MONTH
    from daralla_backend.db.config_db import get_config

    pm = await get_config(CONFIG_KEY_PRICE_MONTH, None)
    p3 = await get_config(CONFIG_KEY_PRICE_3MONTH, None)
    PRICE_MONTH = _parse_price(pm, _ENV_MONTH)
    PRICE_3MONTH = _parse_price(p3, _ENV_3MONTH)
    PRICES["month"] = PRICE_MONTH
    PRICES["3month"] = PRICE_3MONTH
    logger.debug("Цены в памяти: month=%s, 3month=%s", PRICE_MONTH, PRICE_3MONTH)


async def get_default_device_limit_async() -> int:
    """Лимит устройств (limitIp) для новых оплат и пробной подписки по умолчанию."""
    from daralla_backend.db.config_db import get_config

    raw = await get_config(CONFIG_KEY_DEFAULT_DEVICE_LIMIT, "1")
    try:
        return max(1, min(int(float(str(raw).strip())), 100))
    except (ValueError, TypeError):
        return 1
