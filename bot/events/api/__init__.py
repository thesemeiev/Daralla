"""
API модуля событий: public и admin blueprints.
Рефакторен для использования webhook_utils (APIResponse, run_async, @require_admin).
"""
import logging
import time
from flask import Blueprint, request

from ...handlers.webhooks.webhook_utils import (
    APIResponse, run_async, require_admin, require_auth, handle_options, AuthContext
)

logger = logging.getLogger(__name__)

# Кеш для GET /api/events/ (TTL 60 сек)
_events_cache = None
_events_cache_ts = 0
_EVENTS_CACHE_TTL = 60


def create_events_blueprint():
    """Создаёт blueprint событий с unified auth и response handling."""
    bp = Blueprint("events", __name__, url_prefix="/api/events")

    @bp.route("/health", methods=["GET"])
    def health():
        """GET /api/events/health — статус модуля событий."""
        return APIResponse.success(module="events")

    # --- Public: список активных + предстоящих событий ---
    @bp.route("/", methods=["GET", "OPTIONS"])
    @bp.route("", methods=["GET", "OPTIONS"])
    def public_list():
        """GET /api/events — активные и предстоящие события (кеш 60 сек)."""
        if request.method == "OPTIONS":
            return handle_options()
        
        global _events_cache, _events_cache_ts
        
        async def work():
            try:
                # Проверяем кеш
                if _events_cache is not None and (time.time() - _events_cache_ts) < _EVENTS_CACHE_TTL:
                    return APIResponse.success(**_events_cache)
                
                from ..services.event_service import list_active, list_upcoming, list_ended
                active = await list_active()
                upcoming = await list_upcoming()
                ended = await list_ended()
                
                data = {
                    "events": active + upcoming + ended,
                    "active": active,
                    "upcoming": upcoming,
                    "ended": ended
                }
                
                # Обновляем кеш
                globals()["_events_cache"] = data
                globals()["_events_cache_ts"] = time.time()
                
                return APIResponse.success(**data)
            except Exception as e:
                logger.warning("events public list: %s", e)
                return APIResponse.success(events=[], active=[], upcoming=[], ended=[])
        
        return run_async(work())

    # --- Admin: список всех событий ---
    @bp.route("/admin/list", methods=["GET", "OPTIONS"])
    @require_admin
    def admin_list(auth: AuthContext):
        """GET /api/events/admin/list — все события (админ)."""
        if request.method == "OPTIONS":
            return handle_options()
        
        async def work():
            try:
                from ..services.event_service import list_all
                events = await list_all()
                return APIResponse.success(events=events)
            except Exception as e:
                logger.warning("events admin list: %s", e)
                return APIResponse.internal_error(detail=str(e))
        
        return run_async(work())

    # --- Admin: создать событие ---
    @bp.route("/admin/create", methods=["POST", "OPTIONS"])
    @require_admin
    def admin_create(auth: AuthContext):
        """POST /api/events/admin/create — создать событие.
        Body: { name, description?, start_at, end_at, rewards? }
        """
        if request.method == "OPTIONS":
            return handle_options()
        
        try:
            data = request.get_json(silent=True) or {}
            name = (data.get("name") or "").strip()
            description = (data.get("description") or "").strip()
            start_at = (data.get("start_at") or "").strip()
            end_at = (data.get("end_at") or "").strip()
            rewards = data.get("rewards", [])
            
            if not isinstance(rewards, list):
                rewards = []
            
            if not name or not start_at or not end_at:
                return APIResponse.bad_request("name, start_at, end_at required")
            
            async def work():
                try:
                    from ..services.event_service import create_event
                    event_id = await create_event(
                        name, description, start_at, end_at,
                        rewards=rewards, status="active"
                    )
                    globals()["_events_cache"] = None  # инвалидация кеша
                    return APIResponse.success(id=event_id, success=True)
                except ValueError as ve:
                    return APIResponse.bad_request(str(ve))
                except Exception as e:
                    logger.warning("events admin create: %s", e)
                    return APIResponse.internal_error(detail=str(e))
            
            return run_async(work())
        except Exception as e:
            logger.warning("events admin create (parsing): %s", e)
            return APIResponse.bad_request(str(e))

    # --- Admin: редактировать событие ---
    @bp.route("/admin/<int:event_id>", methods=["PUT", "PATCH", "OPTIONS"])
    @require_admin
    def admin_update(auth: AuthContext, event_id):
        """PUT/PATCH /api/events/admin/<id> — редактировать событие (админ)."""
        if request.method == "OPTIONS":
            return handle_options()
        
        try:
            data = request.get_json(silent=True) or {}
            name = (data.get("name") or "").strip() or None
            description = (data.get("description") or "").strip() if "description" in data else None
            start_at = (data.get("start_at") or "").strip() or None
            end_at = (data.get("end_at") or "").strip() or None
            rewards = data.get("rewards") if "rewards" in data else None
            
            if not isinstance(rewards, list) and rewards is not None:
                rewards = None
            
            async def work():
                try:
                    from ..services.event_service import update_event
                    await update_event(
                        event_id, name=name, description=description,
                        start_at=start_at, end_at=end_at, rewards=rewards
                    )
                    globals()["_events_cache"] = None  # инвалидация кеша
                    return APIResponse.success(success=True)
                except ValueError as ve:
                    return APIResponse.bad_request(str(ve))
                except Exception as e:
                    logger.warning("events admin update: %s", e)
                    return APIResponse.internal_error(detail=str(e))
            
            return run_async(work())
        except Exception as e:
            logger.warning("events admin update (parsing): %s", e)
            return APIResponse.bad_request(str(e))

    # --- Admin: удалить событие ---
    @bp.route("/admin/<int:event_id>", methods=["DELETE", "OPTIONS"])
    @require_admin
    def admin_delete(auth: AuthContext, event_id):
        """DELETE /api/events/admin/<id> — удалить событие (админ)."""
        if request.method == "OPTIONS":
            return handle_options()
        
        async def work():
            try:
                from ..services.event_service import delete_event
                ok = await delete_event(event_id)
                if ok:
                    globals()["_events_cache"] = None  # инвалидация кеша
                return APIResponse.success(success=True, deleted=ok)
            except Exception as e:
                logger.warning("events admin delete: %s", e)
                return APIResponse.internal_error(detail=str(e))
        
        return run_async(work())

    # --- Public: мой реферальный код ---
    @bp.route("/my-code", methods=["GET", "OPTIONS"])
    @require_auth
    def public_my_code(auth: AuthContext):
        """GET /api/events/my-code — реферальный код текущего пользователя."""
        if request.method == "OPTIONS":
            return handle_options()
        
        async def work():
            try:
                from ..db.queries import get_or_create_referral_code
                code = await get_or_create_referral_code(str(auth.account_id))
                return APIResponse.success(code=code)
            except Exception as e:
                logger.warning("events my-code: %s", e)
                return APIResponse.internal_error(detail=str(e))
        
        return run_async(work())

    # --- Public: am-i-referred ---
    @bp.route("/am-i-referred", methods=["GET", "OPTIONS"])
    @require_auth
    def public_am_i_referred(auth: AuthContext):
        """GET /api/events/am-i-referred — проверка реферального статуса пользователя."""
        if request.method == "OPTIONS":
            return handle_options()
        
        async def work():
            try:
                from ..db.queries import is_user_already_referred, get_account_first_seen
                referred = await is_user_already_referred(str(auth.account_id))
                first_seen = await get_account_first_seen(str(auth.account_id))
                
                now = int(time.time())
                age_seconds = (now - first_seen) if first_seen else 0
                show_modal = not referred and (first_seen is None or age_seconds < 30 * 86400)
                
                return APIResponse.success(referred=referred, show_modal=show_modal)
            except Exception as e:
                logger.warning("events am-i-referred: %s", e)
                return APIResponse.success(referred=False, show_modal=False)
        
        return run_async(work())

    # --- Public: запись реферала по коду ---
    @bp.route("/record-ref-by-code", methods=["POST", "OPTIONS"])
    @require_auth
    def public_record_ref_by_code(auth: AuthContext):
        """POST /api/events/record-ref-by-code — записать реферал по коду.
        Body: { event_id?, code }
        """
        if request.method == "OPTIONS":
            return handle_options()
        
        try:
            referred_account_id = str(auth.account_id)
            data = request.get_json(silent=True) or {}
            code = (data.get("code") or "").strip()
            
            if not code:
                return APIResponse.bad_request("code required")
            
            event_id = data.get("event_id")
            try:
                event_id = int(event_id) if event_id is not None else None
            except (TypeError, ValueError):
                event_id = None
            
            async def work():
                try:
                    from ..db.queries import (
                        get_account_id_by_code, is_user_already_referred, list_events_active
                    )
                    from ..services.referral_service import record_visit
                    
                    referrer_account_id = await get_account_id_by_code(code)
                    if not referrer_account_id:
                        return APIResponse.bad_request("Код не найден")
                    
                    if referrer_account_id == referred_account_id:
                        return APIResponse.bad_request("Нельзя использовать свой код")
                    
                    if await is_user_already_referred(referred_account_id):
                        return APIResponse.bad_request("Вы уже записаны по приглашению")
                    
                    if event_id is None:
                        active = await list_events_active()
                        if not active:
                            return APIResponse.bad_request("Сейчас нет активных событий")
                        event_id = active[0]["id"]
                    
                    ok = await record_visit(referrer_account_id, referred_account_id, event_id)
                    return APIResponse.success(success=True, recorded=ok)
                except Exception as e:
                    logger.warning("events record-ref-by-code: %s", e)
                    return APIResponse.internal_error(detail=str(e))
            
            return run_async(work())
        except Exception as e:
            logger.warning("events record-ref-by-code (parsing): %s", e)
            return APIResponse.bad_request(str(e))

    # --- Public: детали события ---
    @bp.route("/<int:event_id>", methods=["GET", "OPTIONS"])
    def public_event_detail(event_id):
        """GET /api/events/<id> — детали события."""
        if request.method == "OPTIONS":
            return handle_options()
        
        async def work():
            try:
                from ..services.event_service import get_event
                from ..config import EVENTS_SUPPORT_URL
                
                ev = await get_event(event_id)
                if not ev:
                    return APIResponse.not_found("Event not found")
                
                ev["support_url"] = EVENTS_SUPPORT_URL
                return APIResponse.success(**ev)
            except Exception as e:
                logger.warning("events detail: %s", e)
                return APIResponse.internal_error(detail=str(e))
        
        return run_async(work())

    # --- Public: лидерборд события ---
    @bp.route("/<int:event_id>/leaderboard", methods=["GET", "OPTIONS"])
    def public_leaderboard(event_id):
        """GET /api/events/<id>/leaderboard — топ рефереров в событии."""
        if request.method == "OPTIONS":
            return handle_options()
        
        async def work():
            try:
                limit = min(100, max(1, int(request.args.get("limit", 10))))
                from ..db.queries import get_leaderboard
                rows = await get_leaderboard(event_id, limit=limit)
                return APIResponse.success(leaderboard=rows)
            except Exception as e:
                logger.warning("events leaderboard: %s", e)
                return APIResponse.success(leaderboard=[])
        
        return run_async(work())

    # --- Public: моё место в рейтинге ---
    @bp.route("/<int:event_id>/my-place", methods=["GET", "OPTIONS"])
    @require_auth
    def public_my_place(auth: AuthContext, event_id):
        """GET /api/events/<id>/my-place — место пользователя в рейтинге."""
        if request.method == "OPTIONS":
            return handle_options()
        
        async def work():
            try:
                from ..db.queries import get_my_place
                result = await get_my_place(event_id, str(auth.account_id))
                return APIResponse.success(place=result)
            except Exception as e:
                logger.warning("events my-place: %s", e)
                return APIResponse.success(place=None)
        
        return run_async(work())

    return bp
