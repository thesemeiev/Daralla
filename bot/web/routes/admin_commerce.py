"""
Quart Blueprint: GET/POST /api/admin/commerce — цены и лимит устройств по умолчанию.
"""
from quart import Blueprint, request, jsonify

from bot.web.routes.admin_common import _cors_headers, admin_route
from bot.db.config_db import set_config
from bot.prices_config import (
    CONFIG_KEY_DEFAULT_DEVICE_LIMIT,
    CONFIG_KEY_PRICE_3MONTH,
    CONFIG_KEY_PRICE_MONTH,
    PRICE_3MONTH,
    PRICE_MONTH,
    PRICES,
    refresh_prices_from_db,
    get_default_device_limit_async,
)


def create_blueprint(bot_app):
    bp = Blueprint("admin_commerce", __name__)

    @bp.route("/api/admin/commerce", methods=["GET", "POST", "OPTIONS"])
    @admin_route
    async def api_admin_commerce(request, admin_id):
        if request.method == "GET":
            await refresh_prices_from_db()
            default_dl = await get_default_device_limit_async()
            return jsonify({
                "success": True,
                "price_month": PRICES.get("month", PRICE_MONTH),
                "price_3month": PRICES.get("3month", PRICE_3MONTH),
                "default_device_limit": default_dl,
            }), 200, _cors_headers()

        data = await request.get_json(silent=True) or {}
        try:
            pm = int(data.get("price_month", PRICE_MONTH))
            p3 = int(data.get("price_3month", PRICE_3MONTH))
            dl = int(data.get("default_device_limit", 1))
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Некорректные числовые значения"}), 400, _cors_headers()

        if pm < 1 or pm > 2_000_000 or p3 < 1 or p3 > 2_000_000:
            return jsonify({"success": False, "error": "Цена вне допустимого диапазона"}), 400, _cors_headers()
        if dl < 1 or dl > 100:
            return jsonify({"success": False, "error": "Лимит устройств: от 1 до 100"}), 400, _cors_headers()

        ok = (
            await set_config(CONFIG_KEY_PRICE_MONTH, str(pm), "Цена 1 месяц (₽)")
            and await set_config(CONFIG_KEY_PRICE_3MONTH, str(p3), "Цена 3 месяца (₽)")
            and await set_config(CONFIG_KEY_DEFAULT_DEVICE_LIMIT, str(dl), "Лимит устройств по умолчанию")
        )
        if not ok:
            return jsonify({"success": False, "error": "Не удалось сохранить настройки"}), 500, _cors_headers()

        await refresh_prices_from_db()

        return jsonify({
            "success": True,
            "price_month": PRICES.get("month", pm),
            "price_3month": PRICES.get("3month", p3),
            "default_device_limit": await get_default_device_limit_async(),
        }), 200, _cors_headers()

    return bp
