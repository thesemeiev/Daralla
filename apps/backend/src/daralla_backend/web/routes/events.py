"""
Quart Blueprint: /api/events — health, список событий, реферальный код, админ CRUD.
Async implementation — без asyncio.new_event_loop / run_until_complete.
"""
import logging

from quart import Blueprint, request, jsonify

from bot.services.events_route_service import (
    get_public_events_payload,
    get_event_leaderboard,
    get_event_my_place,
    get_user_referral_code,
    invalidate_public_events_cache,
    require_authenticated_user,
    require_admin_user,
)
from bot.web.routes.admin_common import CORS_HEADERS
from bot.web.routes.transport import auth_error_payload, error_response

logger = logging.getLogger(__name__)

_CORS = CORS_HEADERS


def create_blueprint():
    """Создаёт Quart blueprint событий (health, my-code, public list, admin CRUD)."""
    bp = Blueprint("events", __name__, url_prefix="/api/events")

    @bp.route("/health", methods=["GET"])
    async def health():
        return jsonify({"status": "ok", "module": "events"}), 200

    @bp.route("/", methods=["GET"])
    @bp.route("", methods=["GET"])
    async def public_list():
        """GET /api/events — активные и предстоящие события (кеш 60 сек)."""
        try:
            payload = await get_public_events_payload()
            return jsonify(payload), 200, _CORS
        except Exception as e:
            logger.warning("events public list: %s", e)
            return jsonify({"events": [], "active": [], "upcoming": [], "ended": []}), 200, _CORS

    @bp.route("/admin/list", methods=["GET", "OPTIONS"])
    async def admin_list():
        if request.method == "OPTIONS":
            return "", 200, _CORS
        body = await request.get_json(silent=True) or {}
        user_id, err = await require_admin_user(request.headers, request.args if request.args else {}, body, request.cookies)
        if err:
            return auth_error_payload(err)
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
        body = await request.get_json(silent=True) or {}
        user_id, err = await require_admin_user(request.headers, request.args if request.args else {}, body, request.cookies)
        if err:
            return auth_error_payload(err)
        try:
            data = body
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
            invalidate_public_events_cache()
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
        data = await request.get_json(silent=True) or {}
        user_id, err = await require_admin_user(request.headers, request.args if request.args else {}, data, request.cookies)
        if err:
            return auth_error_payload(err)
        try:
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
            invalidate_public_events_cache()
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
        body = await request.get_json(silent=True) or {}
        user_id, err = await require_admin_user(request.headers, request.args if request.args else {}, body, request.cookies)
        if err:
            return auth_error_payload(err)
        try:
            from bot.events.services.event_service import delete_event
            ok = await delete_event(event_id)
            if ok:
                invalidate_public_events_cache()
            return jsonify({"success": True, "deleted": ok}), 200, _CORS
        except Exception as e:
            logger.warning("events admin delete: %s", e)
            return jsonify({"error": str(e)}), 500

    @bp.route("/my-code", methods=["GET"])
    async def public_my_code():
        body = await request.get_json(silent=True) or {}
        user_id = await require_authenticated_user(request.headers, request.args or {}, body, request.cookies)
        if not user_id:
            return error_response("Unauthorized", 401)
        try:
            code = await get_user_referral_code(user_id)
            return jsonify({"code": code}), 200, _CORS
        except Exception as e:
            logger.warning("events my-code: %s", e)
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
            rows = await get_event_leaderboard(event_id, limit=limit)
            return jsonify({"leaderboard": rows}), 200, _CORS
        except Exception as e:
            logger.warning("events leaderboard: %s", e)
            return jsonify({"leaderboard": []}), 200, _CORS

    @bp.route("/<int:event_id>/my-place", methods=["GET"])
    async def public_my_place(event_id):
        body = await request.get_json(silent=True) or {}
        user_id = await require_authenticated_user(request.headers, request.args or {}, body, request.cookies)
        if not user_id:
            return error_response("Unauthorized", 401)
        try:
            result = await get_event_my_place(event_id, user_id)
            return jsonify({"place": result}), 200, _CORS
        except Exception as e:
            logger.warning("events my-place: %s", e)
            return jsonify({"place": None}), 200, _CORS

    return bp
