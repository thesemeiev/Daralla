"""
Shared CORS and admin auth for Quart admin blueprints.
"""
import logging
from functools import wraps

from quart import request, jsonify

from bot.handlers.api_support.webhook_auth import authenticate_request_async, check_admin_access_async

logger = logging.getLogger(__name__)

# Единый источник CORS для всех маршрутов (включая GET для api_user и events)
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "*",
}


def _cors_headers():
    return {**CORS_HEADERS, "Content-Type": "application/json"}


async def require_admin(request):
    """
    Async admin auth. Returns (user_id, None) on success, or (None, response_tuple) on failure.
    Usage: user_id, err = await require_admin(request); if err: return err
    """
    body = await request.get_json(silent=True) or {}
    user_id = await authenticate_request_async(request.headers, request.args, body)
    if not user_id:
        return None, (jsonify({"error": "Invalid authentication"}), 401, _cors_headers())
    if not await check_admin_access_async(user_id):
        return None, (jsonify({"error": "Access denied"}), 403, _cors_headers())
    return user_id, None


def admin_route(f):
    """
    Декоратор для админ-роутов: обрабатывает OPTIONS, проверяет require_admin,
    оборачивает вызов в try/except с 500 при необработанном исключении.
    Обработчик получает (request, admin_id, *args, **kwargs), где *args — path-параметры роута.
    """
    @wraps(f)
    async def wrapped(*args, **kwargs):
        if request.method == "OPTIONS":
            return "", 200, _cors_headers()
        admin_id, err = await require_admin(request)
        if err:
            return err
        try:
            return await f(request, admin_id, *args, **kwargs)
        except Exception as e:
            logger.exception("Admin route error: %s", e)
            return jsonify({"error": "Internal server error"}), 500, _cors_headers()
    return wrapped
