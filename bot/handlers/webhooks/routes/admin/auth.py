"""
Маршруты: проверка прав админа.
"""
import logging

from flask import request

from ...webhook_utils import APIResponse, require_admin, handle_options, AuthContext

logger = logging.getLogger(__name__)


def register_auth_routes(bp):
    @bp.route("/api/admin/check", methods=["POST", "OPTIONS"])
    @require_admin
    def api_admin_check(auth: AuthContext):
        if request.method == "OPTIONS":
            return handle_options()
        
        return APIResponse.success(is_admin=auth.is_admin)
