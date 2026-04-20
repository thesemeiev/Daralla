"""Registration and onboarding handlers extracted from api_user routes."""

from quart import jsonify, request

from daralla_backend.handlers.api_support.webhook_auth import verify_telegram_init_data
from daralla_backend.services.user_registration_service import (
    register_user_with_trial,
)
from daralla_backend.web.routes.admin_common import _cors_headers
from daralla_backend.web.routes.api_user_common import options_response_or_none, require_user_id


async def handle_api_user_register(_auth, logger):
    opt = options_response_or_none()
    if opt:
        return opt
    try:
        data = await request.get_json(silent=True) or {}
        user_id, _ = await require_user_id(_auth)
        init_data = request.args.get("initData") or data.get("initData")
        tg_user_id = verify_telegram_init_data(init_data) if init_data else None
        payload = await register_user_with_trial(user_id=user_id, tg_user_id=str(tg_user_id) if tg_user_id else None, logger=logger)
        return jsonify(payload), 200, _cors_headers()
    except ValueError as e:
        return jsonify({"error": str(e)}), 401, _cors_headers()
    except Exception as e:
        logger.error("Ошибка регистрации пользователя: %s", e, exc_info=True)
        return jsonify({"error": "Internal server error"}), 500, _cors_headers()
