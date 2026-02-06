"""
Маршруты: информация о подписке Remnawave по short_uuid.
"""
import datetime
import logging

from flask import request

from ...webhook_utils import APIResponse, require_admin, handle_options, run_async, AuthContext

logger = logging.getLogger(__name__)


def register_subscription_routes(bp):
    @bp.route("/api/admin/subscription/by-short-uuid", methods=["POST", "OPTIONS"])
    @require_admin
    def api_admin_subscription_by_short_uuid(auth: AuthContext):
        if request.method == "OPTIONS":
            return handle_options()
        
        data = request.get_json(silent=True) or {}
        short_uuid = (data.get("short_uuid") or data.get("shortUuid") or "").strip()
        if not short_uuid:
            return APIResponse.bad_request('short_uuid required')
        
        async def fetch():
            try:
                from .....services.remnawave_service import RemnawaveClient, load_remnawave_config
                cfg = load_remnawave_config()
                client = RemnawaveClient(cfg)
                info = await client.get_sub_info(short_uuid)
            except Exception as remna_e:
                logger.warning("Remnawave get_sub_info failed: %s", remna_e)
                return APIResponse.internal_error(f'Remnawave unavailable or short_uuid not found')
            
            # Remnawave OpenAPI: GetSubscriptionInfoResponseDto has response.user.expiresAt
            obj = info.get("response") or info.get("obj") or info.get("data") or info
            from .....services.subscription_service import _extract_expiry_from_obj
            exp_ts = _extract_expiry_from_obj(obj) if isinstance(obj, dict) else 0
            if exp_ts == 0 and isinstance(obj, dict):
                for v in obj.values():
                    if isinstance(v, dict):
                        exp_ts = _extract_expiry_from_obj(v)
                        if exp_ts > 0:
                            break
            
            return APIResponse.success(
                subscription={
                    "short_uuid": short_uuid,
                    "expires_at": exp_ts,
                    "expires_at_formatted": datetime.datetime.fromtimestamp(exp_ts).strftime("%d.%m.%Y %H:%M") if exp_ts else None,
                    "raw": obj,
                }
            )
        
        try:
            return run_async(fetch())
        except Exception as e:
            logger.error("Ошибка в /api/admin/subscription/by-short-uuid: %s", e, exc_info=True)
            return APIResponse.internal_error()
