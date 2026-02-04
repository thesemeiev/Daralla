"""
Маршруты: проверка прав админа.
"""
import logging

from flask import request, jsonify

from ...webhook_auth import authenticate_request, check_admin_access
from ._common import CORS_HEADERS, options_response

logger = logging.getLogger(__name__)


def register_auth_routes(bp):
    @bp.route("/api/admin/check", methods=["POST", "OPTIONS"])
    def api_admin_check():
        if request.method == "OPTIONS":
            return options_response()
        try:
            user_id = authenticate_request()
            if not user_id:
                return jsonify({"error": "Invalid authentication"}), 401, CORS_HEADERS
            is_admin = check_admin_access(user_id)
            return (
                jsonify({"success": True, "is_admin": is_admin}),
                200,
                {**CORS_HEADERS, "Content-Type": "application/json"},
            )
        except Exception as e:
            logger.error("Ошибка в /api/admin/check: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500, CORS_HEADERS
