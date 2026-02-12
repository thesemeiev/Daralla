"""
Quart Blueprint: /api/events — health, список событий, реферальный код, админ CRUD.
Async implementation — без asyncio.new_event_loop / run_until_complete.
"""
import logging
import time

from quart import Blueprint, request, jsonify

from bot.web.routes.admin_common import CORS_HEADERS

logger = logging.getLogger(__name__)

_CORS = CORS_HEADERS

# Кеш для GET /api/events/ (TTL 60 сек)
_events_cache = None
_events_cache_ts = 0
_EVENTS_CACHE_TTL = 60


def create_blueprint():
    """Создаёт Quart blueprint событий (health, my-code, record-ref-by-code, public list, admin CRUD)."""
    bp = Blueprint("events", __name__, url_prefix="/api/events")

    @bp.route("/health", methods=["GET"])
    async def health():
        return jsonify({"status": "ok", "module": "events"}), 200

    @bp.route("/", methods=["GET"])
    @bp.route("", methods=["GET"])
    async def public_list():
        """GET /api/events — активные и предстоящие события (кеш 60 сек)."""
        global _events_cache, _events_cache_ts
        try:
            if _events_cache is not None and (time.time() - _events_cache_ts) < _EVENTS_CACHE_TTL:
                return jsonify(_events_cache), 200, _CORS
            from bot.events.services.event_service import list_active, list_upcoming, list_ended
            active = await list_active()
            upcoming = await list_upcoming()
            ended = await list_ended()
            data = {"events": active + upcoming + ended, "active": active, "upcoming": upcoming, "ended": ended}
            _events_cache = data
            _events_cache_ts = time.time()
            return jsonify(data), 200, _CORS
        except Exception as e:
            logger.warning("events public list: %s", e)
            return jsonify({"events": [], "active": [], "upcoming": [], "ended": []}), 200, _CORS

    async def _admin_check():
        from bot.handlers.webhooks.webhook_auth import authenticate_request_async, check_admin_access_async
        body = await request.get_json(silent=True) or {}
        args = request.args if request.args else {}
        user_id = await authenticate_request_async(request.headers, args, body)
        if not user_id:
            return None, 401
        if not await check_admin_access_async(user_id):
            return None, 403
        return user_id, None

    @bp.route("/admin/list", methods=["GET", "OPTIONS"])
    async def admin_list():
        if request.method == "OPTIONS":
            return "", 200, _CORS
        user_id, err = await _admin_check()
        if err:
            return jsonify({"error": "Unauthorized" if err == 401 else "Access denied"}), err
        try:
            from bot.events.services.event_service import list_all
            events = await list_all()
            return jsonify({"events": events}), 200, _CORS
        except Exception as e:
            logger.warning("events admin list: %s", e)
            return jsonify({"error": str(e)}), 500

    @bp.route("/admin/create", methods=["POST", "OPTIONS"])
    async def admin_create():
        if request.method == "OPTIONS":
            return "", 200, _CORS
        user_id, err = await _admin_check()
        if err:
            return jsonify({"error": "Unauthorized" if err == 401 else "Access denied"}), err
        try:
            data = await request.get_json(silent=True) or {}
            name = (data.get("name") or "").strip()
            description = (data.get("description") or "").strip()
            start_at = (data.get("start_at") or "").strip()
            end_at = (data.get("end_at") or "").strip()
            rewards = data.get("rewards")
            if not isinstance(rewards, list):
                rewards = []
            if not name or not start_at or not end_at:
                return jsonify({"error": "name, start_at, end_at required"}), 400
            from bot.events.services.event_service import create_event
            event_id = await create_event(name, description, start_at, end_at, rewards=rewards, status="active")
            globals()["_events_cache"] = None
            return jsonify({"success": True, "id": event_id}), 200, _CORS
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:
            logger.warning("events admin create: %s", e)
            return jsonify({"error": str(e)}), 500

    @bp.route("/admin/<int:event_id>", methods=["PUT", "PATCH", "OPTIONS"])
    async def admin_update(event_id):
        if request.method == "OPTIONS":
            return "", 200, _CORS
        user_id, err = await _admin_check()
        if err:
            return jsonify({"error": "Unauthorized" if err == 401 else "Access denied"}), err
        try:
            data = await request.get_json(silent=True) or {}
            name = (data.get("name") or "").strip() or None
            description = (data.get("description") or "").strip() if "description" in data else None
            start_at = (data.get("start_at") or "").strip() or None
            end_at = (data.get("end_at") or "").strip() or None
            rewards = data.get("rewards") if "rewards" in data else None
            if not isinstance(rewards, list):
                rewards = None
            from bot.events.services.event_service import update_event
            await update_event(event_id, name=name, description=description,
                              start_at=start_at, end_at=end_at, rewards=rewards)
            globals()["_events_cache"] = None
            return jsonify({"success": True}), 200, _CORS
        except ValueError as ve:
            return jsonify({"error": str(ve)}), 400
        except Exception as e:
            logger.warning("events admin update: %s", e)
            return jsonify({"error": str(e)}), 500

    @bp.route("/admin/<int:event_id>", methods=["DELETE", "OPTIONS"])
    async def admin_delete(event_id):
        if request.method == "OPTIONS":
            return "", 200, _CORS
        user_id, err = await _admin_check()
        if err:
            return jsonify({"error": "Unauthorized" if err == 401 else "Access denied"}), err
        try:
            from bot.events.services.event_service import delete_event
            ok = await delete_event(event_id)
            if ok:
                globals()["_events_cache"] = None
            return jsonify({"success": True, "deleted": ok}), 200, _CORS
        except Exception as e:
            logger.warning("events admin delete: %s", e)
            return jsonify({"error": str(e)}), 500

    @bp.route("/my-code", methods=["GET"])
    async def public_my_code():
        from bot.handlers.webhooks.webhook_auth import authenticate_request_async
        body = await request.get_json(silent=True) or {}
        user_id = await authenticate_request_async(request.headers, request.args or {}, body)
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401
        try:
            from bot.events.db.queries import get_or_create_referral_code
            code = await get_or_create_referral_code(user_id)
            return jsonify({"code": code}), 200, _CORS
        except Exception as e:
            logger.warning("events my-code: %s", e)
            return jsonify({"error": str(e)}), 500

    @bp.route("/am-i-referred", methods=["GET"])
    async def public_am_i_referred():
        from bot.handlers.webhooks.webhook_auth import authenticate_request_async
        body = await request.get_json(silent=True) or {}
        user_id = await authenticate_request_async(request.headers, request.args or {}, body)
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401
        try:
            from bot.events.db.queries import is_user_already_referred, get_user_first_seen
            referred = await is_user_already_referred(user_id)
            first_seen = await get_user_first_seen(user_id)
            now = int(time.time())
            age_seconds = (now - first_seen) if first_seen else 0
            show_modal = not referred and (first_seen is None or age_seconds < 30 * 86400)
            return jsonify({"referred": referred, "show_modal": show_modal}), 200, _CORS
        except Exception as e:
            logger.warning("events am-i-referred: %s", e)
            return jsonify({"error": str(e)}), 500

    @bp.route("/record-ref-by-code", methods=["POST", "OPTIONS"])
    async def public_record_ref_by_code():
        if request.method == "OPTIONS":
            return "", 200, _CORS
        from bot.handlers.webhooks.webhook_auth import authenticate_request_async
        body = await request.get_json(silent=True) or {}
        user_id = await authenticate_request_async(request.headers, request.args or {}, body)
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401
        code = (body.get("code") or "").strip()
        if not code:
            return jsonify({"error": "code required"}), 400
        event_id = body.get("event_id")
        try:
            event_id = int(event_id) if event_id is not None else None
        except (TypeError, ValueError):
            event_id = None
        try:
            from bot.events.db.queries import (
                get_user_id_by_code,
                is_user_already_referred,
                list_events_active,
            )
            from bot.events.services.referral_service import record_visit
            referrer_user_id = await get_user_id_by_code(code)
            if not referrer_user_id:
                return jsonify({"error": "Код не найден"}), 400
            if referrer_user_id == user_id:
                return jsonify({"error": "Нельзя использовать свой код"}), 400
            if await is_user_already_referred(user_id):
                return jsonify({"error": "Вы уже записаны по приглашению"}), 400
            if event_id is None:
                active = await list_events_active()
                if not active:
                    return jsonify({"error": "Сейчас нет активных событий"}), 400
                event_id = active[0]["id"]
            ok = await record_visit(referrer_user_id, user_id, event_id)
            return jsonify({"success": True, "recorded": ok}), 200, _CORS
        except Exception as e:
            logger.warning("events record-ref-by-code: %s", e)
            return jsonify({"error": str(e)}), 500

    @bp.route("/<int:event_id>", methods=["GET"])
    async def public_event_detail(event_id):
        try:
            from bot.events.services.event_service import get_event
            from bot.events.config import EVENTS_SUPPORT_URL
            ev = await get_event(event_id)
            if not ev:
                return jsonify({"error": "Not found"}), 404
            ev["support_url"] = EVENTS_SUPPORT_URL
            return jsonify(ev), 200, _CORS
        except Exception as e:
            logger.warning("events detail: %s", e)
            return jsonify({"error": str(e)}), 500

    @bp.route("/<int:event_id>/leaderboard", methods=["GET"])
    async def public_leaderboard(event_id):
        try:
            limit_arg = request.args.get("limit", 10)
            limit = min(100, max(1, int(limit_arg)))
        except (TypeError, ValueError):
            limit = 10
        try:
            from bot.events.db.queries import get_leaderboard
            rows = await get_leaderboard(event_id, limit=limit)
            return jsonify({"leaderboard": rows}), 200, _CORS
        except Exception as e:
            logger.warning("events leaderboard: %s", e)
            return jsonify({"leaderboard": []}), 200, _CORS

    @bp.route("/<int:event_id>/my-place", methods=["GET"])
    async def public_my_place(event_id):
        from bot.handlers.webhooks.webhook_auth import authenticate_request_async
        body = await request.get_json(silent=True) or {}
        user_id = await authenticate_request_async(request.headers, request.args or {}, body)
        if not user_id:
            return jsonify({"error": "Unauthorized"}), 401
        try:
            from bot.events.db.queries import get_my_place
            result = await get_my_place(event_id, user_id)
            return jsonify({"place": result}), 200, _CORS
        except Exception as e:
            logger.warning("events my-place: %s", e)
            return jsonify({"place": None}), 200, _CORS

    return bp
