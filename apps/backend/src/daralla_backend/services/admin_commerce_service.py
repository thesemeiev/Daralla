"""Service layer for admin commerce endpoints."""

from __future__ import annotations

import json

from daralla_backend.db.config_db import set_config
from daralla_backend.prices_config import (
    CONFIG_KEY_TARIFFS_JSON,
    CONFIG_KEY_DEFAULT_DEVICE_LIMIT,
    CONFIG_KEY_PRICE_3MONTH,
    CONFIG_KEY_PRICE_MONTH,
    PRICE_3MONTH,
    PRICE_MONTH,
    PRICES,
    get_tariffs,
    get_default_device_limit_async,
    normalize_tariffs,
    refresh_prices_from_db,
)


async def admin_commerce_get_payload():
    await refresh_prices_from_db()
    default_dl = await get_default_device_limit_async()
    tariffs = get_tariffs()
    return {
        "success": True,
        "price_month": PRICES.get("month", PRICE_MONTH),
        "price_3month": PRICES.get("3month", PRICE_3MONTH),
        "tariffs": tariffs,
        "default_device_limit": default_dl,
    }, 200


async def admin_commerce_update_payload(data: dict):
    tariffs_payload = data.get("tariffs")
    tariffs_to_save = normalize_tariffs(tariffs_payload) if isinstance(tariffs_payload, list) else []

    if not tariffs_to_save:
        # Legacy mode: поддержка старых полей из UI.
        try:
            pm = int(data.get("price_month", PRICE_MONTH))
            p3 = int(data.get("price_3month", PRICE_3MONTH))
        except (TypeError, ValueError):
            return {"success": False, "error": "Некорректные числовые значения"}, 400
        if pm < 1 or pm > 2_000_000 or p3 < 1 or p3 > 2_000_000:
            return {"success": False, "error": "Цена вне допустимого диапазона"}, 400
        tariffs_to_save = [
            {"period": "month", "title": "1 месяц", "days": 30, "price": pm, "badge": ""},
            {"period": "3month", "title": "3 месяца", "days": 90, "price": p3, "badge": "best"},
        ]

    if len(tariffs_to_save) == 0:
        return {"success": False, "error": "Добавьте хотя бы один тариф"}, 400

    if len(tariffs_to_save) > 20:
        return {"success": False, "error": "Слишком много тарифов (максимум 20)"}, 400

    try:
        dl = int(data.get("default_device_limit", 1))
    except (TypeError, ValueError):
        return {"success": False, "error": "Некорректный лимит устройств"}, 400
    if dl < 1 or dl > 100:
        return {"success": False, "error": "Лимит устройств: от 1 до 100"}, 400

    month_price = next((int(t["price"]) for t in tariffs_to_save if t.get("period") == "month"), None)
    three_price = next((int(t["price"]) for t in tariffs_to_save if t.get("period") == "3month"), None)
    if month_price is None:
        month_price = int(tariffs_to_save[0]["price"])
    if three_price is None:
        three_price = month_price

    ok = await set_config(
        CONFIG_KEY_TARIFFS_JSON,
        json.dumps(tariffs_to_save, ensure_ascii=False),
        "Тарифы подписок (JSON)",
    )
    ok = ok and await set_config(CONFIG_KEY_PRICE_MONTH, str(month_price), "Цена 1 месяц (₽)")
    ok = ok and await set_config(CONFIG_KEY_PRICE_3MONTH, str(three_price), "Цена 3 месяца (₽)")
    ok = ok and await set_config(
        CONFIG_KEY_DEFAULT_DEVICE_LIMIT,
        str(dl),
        "Лимит устройств по умолчанию",
    )
    if not ok:
        return {"success": False, "error": "Не удалось сохранить настройки"}, 500

    await refresh_prices_from_db()
    tariffs = get_tariffs()
    return {
        "success": True,
        "price_month": PRICES.get("month", month_price),
        "price_3month": PRICES.get("3month", three_price),
        "tariffs": tariffs,
        "default_device_limit": await get_default_device_limit_async(),
    }, 200
