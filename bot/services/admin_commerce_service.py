"""Service layer for admin commerce endpoints."""

from __future__ import annotations

from bot.db.config_db import set_config
from bot.prices_config import (
    CONFIG_KEY_DEFAULT_DEVICE_LIMIT,
    CONFIG_KEY_PRICE_3MONTH,
    CONFIG_KEY_PRICE_MONTH,
    PRICE_3MONTH,
    PRICE_MONTH,
    PRICES,
    get_default_device_limit_async,
    refresh_prices_from_db,
)


async def admin_commerce_get_payload():
    await refresh_prices_from_db()
    default_dl = await get_default_device_limit_async()
    return {
        "success": True,
        "price_month": PRICES.get("month", PRICE_MONTH),
        "price_3month": PRICES.get("3month", PRICE_3MONTH),
        "default_device_limit": default_dl,
    }, 200


async def admin_commerce_update_payload(data: dict):
    try:
        pm = int(data.get("price_month", PRICE_MONTH))
        p3 = int(data.get("price_3month", PRICE_3MONTH))
        dl = int(data.get("default_device_limit", 1))
    except (TypeError, ValueError):
        return {"success": False, "error": "Некорректные числовые значения"}, 400

    if pm < 1 or pm > 2_000_000 or p3 < 1 or p3 > 2_000_000:
        return {"success": False, "error": "Цена вне допустимого диапазона"}, 400
    if dl < 1 or dl > 100:
        return {"success": False, "error": "Лимит устройств: от 1 до 100"}, 400

    ok = (
        await set_config(CONFIG_KEY_PRICE_MONTH, str(pm), "Цена 1 месяц (₽)")
        and await set_config(CONFIG_KEY_PRICE_3MONTH, str(p3), "Цена 3 месяца (₽)")
        and await set_config(
            CONFIG_KEY_DEFAULT_DEVICE_LIMIT,
            str(dl),
            "Лимит устройств по умолчанию",
        )
    )
    if not ok:
        return {"success": False, "error": "Не удалось сохранить настройки"}, 500

    await refresh_prices_from_db()
    return {
        "success": True,
        "price_month": PRICES.get("month", pm),
        "price_3month": PRICES.get("3month", p3),
        "default_device_limit": await get_default_device_limit_async(),
    }, 200
