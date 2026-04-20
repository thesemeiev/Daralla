"""Subscription-related handlers extracted from api_user routes."""

from quart import jsonify, request

from bot.services.user_subscriptions_service import (
    rename_subscription_for_user,
    server_usage_payload,
    subscriptions_overview_payload,
)
from bot.web.routes.admin_common import _cors_headers
from bot.web.routes.api_user_common import options_response_or_none, require_user_id
from bot.web.routes.api_user_helpers import normalize_map_lat_lng


async def handle_api_subscriptions(_auth, logger):
    opt = options_response_or_none()
    if opt:
        return opt
    try:
        user_id, err = await require_user_id(_auth)
        if err:
            return jsonify(err[0]), err[1]
        payload = await subscriptions_overview_payload(user_id)
        resp = jsonify(payload)
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        return resp, 200, _cors_headers()
    except Exception as e:
        logger.error("Ошибка в API /api/subscriptions: %s", e, exc_info=True)
        return jsonify({"error": "Internal server error"}), 500, _cors_headers()


async def handle_api_user_subscription_rename(_auth, sub_id, logger):
    opt = options_response_or_none()
    if opt:
        return opt
    try:
        user_id, err = await require_user_id(_auth)
        if err:
            return jsonify(err[0]), err[1]
        data = await request.get_json(silent=True) or {}
        new_name = (data.get("name") or "").strip()
        if not new_name:
            return jsonify({"error": "Name is required"}), 400
        renamed = await rename_subscription_for_user(sub_id, user_id, new_name)
        if not renamed:
            return jsonify({"error": "Subscription not found or access denied"}), 404
        return (
            jsonify(
                {
                    "success": True,
                    "message": "Subscription renamed successfully",
                    "name": new_name,
                }
            ),
            200,
            _cors_headers(),
        )
    except Exception as e:
        logger.error("Ошибка в API /api/user/subscription/%s/rename: %s", sub_id, e, exc_info=True)
        return jsonify({"error": "Internal server error"}), 500, _cors_headers()


async def handle_api_user_server_usage(_auth, logger):
    opt = options_response_or_none()
    if opt:
        return opt
    try:
        user_id, err = await require_user_id(_auth)
        if err:
            return jsonify(err[0]), err[1]
        from bot.app_context import get_ctx

        server_manager = get_ctx().server_manager
        payload = await server_usage_payload(user_id, server_manager, normalize_map_lat_lng)
        return jsonify(payload), 200, _cors_headers()
    except Exception as e:
        logger.error("Ошибка в API /api/user/server-usage: %s", e, exc_info=True)
        return jsonify({"error": "Internal server error"}), 500, _cors_headers()
