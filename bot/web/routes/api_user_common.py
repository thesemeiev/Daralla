"""Shared helpers for api_user route handlers."""

from __future__ import annotations

from quart import request

from bot.handlers.api_support.webhook_auth import authenticate_request_async
from bot.web.routes.admin_common import CORS_HEADERS


def options_response_or_none():
    """Return standard CORS response for OPTIONS requests, else None."""
    if request.method == "OPTIONS":
        return "", 200, CORS_HEADERS
    return None


async def require_user_id(_auth, error_message: str = "Invalid authentication"):
    """
    Resolve authenticated user id.

    Returns tuple: (user_id, error_response_or_none)
    """
    user_id = await _auth()
    if user_id:
        return user_id, None
    return None, ({"error": error_message}, 401)


async def auth_user_from_request():
    """Shared auth resolver for api_user routes."""
    body = await request.get_json(silent=True) or {}
    return await authenticate_request_async(request.headers, request.args, body, request.cookies)
