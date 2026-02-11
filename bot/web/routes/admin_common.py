"""
Shared CORS and admin auth for Quart admin blueprints.
"""
import logging

from quart import request, jsonify

from bot.handlers.webhooks.webhook_auth import authenticate_request_async, check_admin_access_async

logger = logging.getLogger(__name__)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
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
