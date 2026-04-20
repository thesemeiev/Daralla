"""Payment handlers extracted from api_user routes."""

from quart import jsonify, request

from daralla_backend.services.user_payments_service import (
    UserPaymentServiceError,
    create_user_payment,
    user_payment_status_payload,
)
from daralla_backend.web.routes.admin_common import CORS_HEADERS, _cors_headers
from daralla_backend.web.routes.api_user_common import options_response_or_none, require_user_id


async def handle_api_user_payment_create(_auth, logger):
    opt = options_response_or_none()
    if opt:
        return opt
    try:
        user_id, err = await require_user_id(_auth)
        if err:
            return jsonify(err[0]), err[1]
        data = await request.get_json(silent=True) or {}
        period = data.get("period")
        subscription_id = data.get("subscription_id")
        referrer_code = (data.get("referrer_code") or "").strip()
        gateway = (data.get("gateway") or "yookassa").strip().lower()
        payload = await create_user_payment(
            user_id=user_id,
            period=period,
            subscription_id=subscription_id,
            referrer_code=referrer_code,
            gateway=gateway,
            logger=logger,
        )
        return jsonify(payload), 200, _cors_headers()
    except UserPaymentServiceError as e:
        return jsonify({"error": e.message}), e.status_code, _cors_headers()
    except Exception as e:
        logger.error("Ошибка в API /api/user/payment/create: %s", e, exc_info=True)
        return jsonify({"error": "Internal server error"}), 500, _cors_headers()


async def handle_api_user_payment_status(_auth, payment_id, logger):
    opt = options_response_or_none()
    if opt:
        return opt
    try:
        user_id, err = await require_user_id(_auth)
        if err:
            return jsonify(err[0]), err[1]
        payload = await user_payment_status_payload(user_id=user_id, payment_id=payment_id)
        return jsonify(payload), 200, _cors_headers()
    except UserPaymentServiceError as e:
        return jsonify({"error": e.message}), e.status_code, _cors_headers()
    except Exception as e:
        logger.error("Ошибка в API /api/user/payment/status/%s: %s", payment_id, e, exc_info=True)
        return jsonify({"error": "Internal server error"}), 500, _cors_headers()
