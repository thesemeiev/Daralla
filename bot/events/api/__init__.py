"""
API модуля событий: public и admin blueprints.
"""
import asyncio
import logging
import time
from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

_CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS", "Access-Control-Allow-Headers": "*"}

# Rate limit для record-ref: макс 10 запросов на user_id в минуту
_record_ref_counts = {}
_record_ref_cleanup = 0
_RECORD_REF_LIMIT = 10
_RECORD_REF_WINDOW = 60

# Кеш для GET /api/events/ (TTL 60 сек)
_events_cache = None
_events_cache_ts = 0
_EVENTS_CACHE_TTL = 60


def create_events_blueprint():
    """Создаёт blueprint событий (health, record-ref, public list, admin CRUD)."""
    bp = Blueprint("events", __name__, url_prefix="/api/events")

    @bp.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "module": "events"}), 200

    @bp.route("/record-ref", methods=["POST", "OPTIONS"])
    def record_ref():
        """Записать реферальный визит: текущий пользователь пришёл по ссылке ref (referrer_user_id)."""
        if request.method == "OPTIONS":
            return ("", 200, _CORS)
        try:
            from bot.handlers.webhooks.webhook_auth import authenticate_request
            user_id = authenticate_request()
            if not user_id:
                return jsonify({"error": "Unauthorized"}), 401
            # Rate limit
            global _record_ref_counts, _record_ref_cleanup
            now = time.time()
            if now - _record_ref_cleanup > 120:
                _record_ref_counts = {k: v for k, v in _record_ref_counts.items() if v["t"] > now - _RECORD_REF_WINDOW}
                _record_ref_cleanup = now
            entry = _record_ref_counts.get(user_id, {"c": 0, "t": now})
            if entry["t"] < now - _RECORD_REF_WINDOW:
                entry = {"c": 0, "t": now}
            entry["c"] += 1
            _record_ref_counts[user_id] = entry
            if entry["c"] > _RECORD_REF_LIMIT:
                return jsonify({"error": "Too many requests"}), 429
            data = request.get_json(silent=True) or {}
            ref = (data.get("ref") or request.args.get("ref") or "").strip()
            if not ref:
                return jsonify({"error": "ref required"}), 400
            if ref == user_id:
                return jsonify({"success": True, "skipped": "self"}), 200
            event_id = data.get("event_id") or request.args.get("event_id")
            try:
                event_id = int(event_id) if event_id is not None else None
            except (TypeError, ValueError):
                event_id = None
            if event_id is None:
                return jsonify({"error": "event_id required"}), 400
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from bot.events.services.referral_service import record_visit
                ok = loop.run_until_complete(record_visit(ref, user_id, event_id=event_id))
                return jsonify({"success": True, "recorded": ok}), 200
            finally:
                loop.close()
        except Exception as e:
            logger.warning("record-ref: %s", e)
            return jsonify({"error": str(e)}), 500

    # --- Public: список активных + предстоящих событий ---
    @bp.route("/", methods=["GET"])
    @bp.route("", methods=["GET"])
    def public_list():
        """GET /api/events — активные и предстоящие события для пользователя (кеш 60 сек)."""
        global _events_cache, _events_cache_ts
        try:
            cache = _events_cache
            if cache is not None and (time.time() - _events_cache_ts) < _EVENTS_CACHE_TTL:
                return jsonify(cache), 200, {"Content-Type": "application/json", **_CORS}
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from bot.events.services.event_service import list_active, list_upcoming, list_ended
                active = loop.run_until_complete(list_active())
                upcoming = loop.run_until_complete(list_upcoming())
                ended = loop.run_until_complete(list_ended())
                data = {"events": active + upcoming + ended, "active": active, "upcoming": upcoming, "ended": ended}
                _events_cache = data
                _events_cache_ts = time.time()
                return jsonify(data), 200, {"Content-Type": "application/json", **_CORS}
            finally:
                loop.close()
        except Exception as e:
            logger.warning("events public list: %s", e)
            return jsonify({"events": [], "active": [], "upcoming": [], "ended": []}), 200, {"Content-Type": "application/json", **_CORS}

    # --- Admin: создание, список всех, удаление ---
    def _admin_check():
        from bot.handlers.webhooks.webhook_auth import authenticate_request, check_admin_access
        user_id = authenticate_request()
        if not user_id:
            return None, 401
        if not check_admin_access(user_id):
            return None, 403
        return user_id, None

    @bp.route("/admin/list", methods=["GET", "OPTIONS"])
    def admin_list():
        """GET /api/events/admin/list — все события (админ)."""
        if request.method == "OPTIONS":
            return ("", 200, _CORS)
        user_id, err = _admin_check()
        if err:
            return jsonify({"error": "Unauthorized" if err == 401 else "Access denied"}), err
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from bot.events.services.event_service import list_all
                events = loop.run_until_complete(list_all())
                return jsonify({"events": events}), 200, {"Content-Type": "application/json", **_CORS}
            finally:
                loop.close()
        except Exception as e:
            logger.warning("events admin list: %s", e)
            return jsonify({"error": str(e)}), 500

    @bp.route("/admin/create", methods=["POST", "OPTIONS"])
    def admin_create():
        """POST /api/events/admin/create — создать событие (админ). Body: name, description, start_at, end_at, rewards."""
        if request.method == "OPTIONS":
            return ("", 200, _CORS)
        user_id, err = _admin_check()
        if err:
            return jsonify({"error": "Unauthorized" if err == 401 else "Access denied"}), err
        try:
            data = request.get_json(silent=True) or {}
            name = (data.get("name") or "").strip()
            description = (data.get("description") or "").strip()
            start_at = (data.get("start_at") or "").strip()
            end_at = (data.get("end_at") or "").strip()
            rewards = data.get("rewards")
            if not isinstance(rewards, list):
                rewards = []
            if not name or not start_at or not end_at:
                return jsonify({"error": "name, start_at, end_at required"}), 400
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from bot.events.services.event_service import create_event
                event_id = loop.run_until_complete(create_event(name, description, start_at, end_at, rewards=rewards, status="active"))
                globals()["_events_cache"] = None  # инвалидация кеша
                return jsonify({"success": True, "id": event_id}), 200, {"Content-Type": "application/json", **_CORS}
            except ValueError as ve:
                return jsonify({"error": str(ve)}), 400
            finally:
                loop.close()
        except Exception as e:
            logger.warning("events admin create: %s", e)
            return jsonify({"error": str(e)}), 500

    @bp.route("/admin/<int:event_id>", methods=["PUT", "PATCH", "OPTIONS"])
    def admin_update(event_id):
        """PUT/PATCH /api/events/admin/<id> — редактировать событие (админ). Рефералы и рейтинги не затрагиваются."""
        if request.method == "OPTIONS":
            return ("", 200, _CORS)
        user_id, err = _admin_check()
        if err:
            return jsonify({"error": "Unauthorized" if err == 401 else "Access denied"}), err
        try:
            data = request.get_json(silent=True) or {}
            name = (data.get("name") or "").strip() or None
            description = (data.get("description") or "").strip() if "description" in data else None
            start_at = (data.get("start_at") or "").strip() or None
            end_at = (data.get("end_at") or "").strip() or None
            rewards = data.get("rewards") if "rewards" in data else None
            if isinstance(rewards, list):
                pass
            else:
                rewards = None
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from bot.events.services.event_service import update_event
                loop.run_until_complete(update_event(event_id, name=name, description=description,
                    start_at=start_at, end_at=end_at, rewards=rewards))
                globals()["_events_cache"] = None
                return jsonify({"success": True}), 200, {"Content-Type": "application/json", **_CORS}
            except ValueError as ve:
                return jsonify({"error": str(ve)}), 400
            finally:
                loop.close()
        except Exception as e:
            logger.warning("events admin update: %s", e)
            return jsonify({"error": str(e)}), 500

    @bp.route("/admin/<int:event_id>", methods=["DELETE", "OPTIONS"])
    def admin_delete(event_id):
        """DELETE /api/events/admin/<id> — удалить событие (админ)."""
        if request.method == "OPTIONS":
            return ("", 200, _CORS)
        user_id, err = _admin_check()
        if err:
            return jsonify({"error": "Unauthorized" if err == 401 else "Access denied"}), err
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from bot.events.services.event_service import delete_event
                ok = loop.run_until_complete(delete_event(event_id))
                if ok:
                    globals()["_events_cache"] = None
                return jsonify({"success": True, "deleted": ok}), 200, {"Content-Type": "application/json", **_CORS}
            finally:
                loop.close()
        except Exception as e:
            logger.warning("events admin delete: %s", e)
            return jsonify({"error": str(e)}), 500

    # --- Public: моя реферальная ссылка (до <int:event_id>, иначе my-ref-link матчится как id) ---
    @bp.route("/my-ref-link", methods=["GET"])
    def public_my_ref_link():
        """GET /api/events/my-ref-link — реферальная ссылка текущего пользователя (event_id обязателен)."""
        try:
            from bot.handlers.webhooks.webhook_auth import authenticate_request
            user_id = authenticate_request()
            if not user_id:
                return jsonify({"error": "Unauthorized"}), 401
            event_id = request.args.get("event_id", "").strip()
            try:
                event_id = int(event_id) if event_id else None
            except ValueError:
                event_id = None
            if event_id is None:
                return jsonify({"error": "event_id required"}), 400
            import os
            base = (os.environ.get("WEBSITE_URL") or request.url_root or "").rstrip("/")
            if not base:
                base = (request.host_url or "").rstrip("/")
            ref_link = base + "/?ref=" + user_id if base else "?ref=" + user_id
            if event_id:
                ref_link += "&event_id=" + str(event_id)
            return jsonify({"ref_link": ref_link, "user_id": user_id, "event_id": event_id}), 200, {"Content-Type": "application/json", **_CORS}
        except Exception as e:
            logger.warning("events my-ref-link: %s", e)
            return jsonify({"error": str(e)}), 500

    # --- Public: детали события, рейтинг, моё место ---
    @bp.route("/<int:event_id>", methods=["GET"])
    def public_event_detail(event_id):
        """GET /api/events/<id> — детали события."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from bot.events.services.event_service import get_event
                from bot.events.config import EVENTS_SUPPORT_URL
                ev = loop.run_until_complete(get_event(event_id))
                if not ev:
                    return jsonify({"error": "Not found"}), 404
                ev["support_url"] = EVENTS_SUPPORT_URL
                return jsonify(ev), 200, {"Content-Type": "application/json", **_CORS}
            finally:
                loop.close()
        except Exception as e:
            logger.warning("events detail: %s", e)
            return jsonify({"error": str(e)}), 500

    @bp.route("/<int:event_id>/leaderboard", methods=["GET"])
    def public_leaderboard(event_id):
        """GET /api/events/<id>/leaderboard — топ рефереров (limit из query, по умолчанию 10)."""
        try:
            limit = min(100, max(1, int(request.args.get("limit", 10))))
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from bot.events.db.queries import get_leaderboard
                rows = loop.run_until_complete(get_leaderboard(event_id, limit=limit))
                return jsonify({"leaderboard": rows}), 200, {"Content-Type": "application/json", **_CORS}
            finally:
                loop.close()
        except Exception as e:
            logger.warning("events leaderboard: %s", e)
            return jsonify({"leaderboard": []}), 200, {"Content-Type": "application/json", **_CORS}

    @bp.route("/<int:event_id>/my-place", methods=["GET"])
    def public_my_place(event_id):
        """GET /api/events/<id>/my-place — место текущего пользователя в рейтинге."""
        try:
            from bot.handlers.webhooks.webhook_auth import authenticate_request
            user_id = authenticate_request()
            if not user_id:
                return jsonify({"error": "Unauthorized"}), 401
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from bot.events.db.queries import get_my_place
                result = loop.run_until_complete(get_my_place(event_id, user_id))
                return jsonify({"place": result}), 200, {"Content-Type": "application/json", **_CORS}
            finally:
                loop.close()
        except Exception as e:
            logger.warning("events my-place: %s", e)
            return jsonify({"place": None}), 200, {"Content-Type": "application/json", **_CORS}

    return bp
