"""
Маршруты: информация о подписке Remnawave по short_uuid.
"""
import datetime
import logging

from flask import request, jsonify

from ...webhook_auth import authenticate_request, check_admin_access
from ._common import CORS_HEADERS, options_response

logger = logging.getLogger(__name__)


def register_subscription_routes(bp):
    @bp.route("/api/admin/subscription/by-short-uuid", methods=["POST", "OPTIONS"])
    def api_admin_subscription_by_short_uuid():
        if request.method == "OPTIONS":
            return options_response()
        try:
            admin_id = authenticate_request()
            if not admin_id or not check_admin_access(admin_id):
                return jsonify({"error": "Access denied"}), 403
            data = request.get_json(silent=True) or {}
            short_uuid = (data.get("short_uuid") or data.get("shortUuid") or "").strip()
            if not short_uuid:
                return jsonify({"error": "short_uuid required"}), 400
            try:
                from .....services.remnawave_service import RemnawaveClient, load_remnawave_config
                cfg = load_remnawave_config()
                client = RemnawaveClient(cfg)
                info = client.get_sub_info(short_uuid)
            except Exception as remna_e:
                logger.warning("Remnawave get_sub_info failed: %s", remna_e)
                return jsonify({"error": "Remnawave unavailable or short_uuid not found", "detail": str(remna_e)}), 502
            obj = info.get("obj") or info.get("data") or info
            from .....services.subscription_service import _parse_expiry_to_timestamp
            raw_exp = obj.get("expiresAt") or obj.get("expires_at") or obj.get("expiryTime") or 0
            exp_ts = _parse_expiry_to_timestamp(raw_exp)
            return (
                jsonify({
                    "success": True,
                    "subscription": {
                        "short_uuid": short_uuid,
                        "expires_at": exp_ts,
                        "expires_at_formatted": datetime.datetime.fromtimestamp(exp_ts).strftime("%d.%m.%Y %H:%M") if exp_ts else None,
                        "raw": obj,
                    },
                }),
                200,
                {**CORS_HEADERS, "Content-Type": "application/json"},
            )
        except Exception as e:
            logger.error("Ошибка в /api/admin/subscription/by-short-uuid: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500
