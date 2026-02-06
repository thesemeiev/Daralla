"""
Унифицированные утилиты для webhook API:
- Аутентификация (один вход для Telegram + Web)
- Ответы API (единый формат)
- CORS headers
- Декораторы для обработчиков
"""
import asyncio
import functools
import logging
from typing import Optional, Dict, Any, Tuple, Callable
from flask import request, jsonify, Response

from .webhook_auth import authenticate_request as _authenticate_request, verify_telegram_init_data, check_admin_access

logger = logging.getLogger(__name__)


# ============ API Response Format ============

class APIResponse:
    """Единый формат ответа API"""
    
    @staticmethod
    def success(data: Optional[Dict[str, Any]] = None, **kwargs) -> Tuple[Response, int, Dict]:
        """Успешный ответ с данными"""
        payload = {"success": True}
        if data:
            payload.update(data)
        payload.update(kwargs)  # Allow inline kwargs like success(count=5, items=[...])
        return jsonify(payload), 200, APIResponse.cors_headers()
    
    @staticmethod
    def error(message: str, code: int = 400, error_code: Optional[str] = None) -> Tuple[Response, int, Dict]:
        """Ошибка"""
        payload = {
            "success": False,
            "error": message,
        }
        if error_code:
            payload["error_code"] = error_code
        return jsonify(payload), code, APIResponse.cors_headers()
    
    @staticmethod
    def unauthorized(message: str = "Unauthorized") -> Tuple[Response, int, Dict]:
        """401 Unauthorized"""
        return APIResponse.error(message, 401, "UNAUTHORIZED")
    
    @staticmethod
    def forbidden(message: str = "Forbidden") -> Tuple[Response, int, Dict]:
        """403 Forbidden"""
        return APIResponse.error(message, 403, "FORBIDDEN")
    
    @staticmethod
    def not_found(message: str = "Not found") -> Tuple[Response, int, Dict]:
        """404 Not found"""
        return APIResponse.error(message, 404, "NOT_FOUND")
    
    @staticmethod
    def bad_request(message: str) -> Tuple[Response, int, Dict]:
        """400 Bad request"""
        return APIResponse.error(message, 400, "BAD_REQUEST")
    
    @staticmethod
    def conflict(message: str, error_code: str = "CONFLICT") -> Tuple[Response, int, Dict]:
        """409 Conflict"""
        return APIResponse.error(message, 409, error_code)
    
    @staticmethod
    def internal_error(message: str = "Internal server error") -> Tuple[Response, int, Dict]:
        """500 Internal server error"""
        return APIResponse.error(message, 500, "INTERNAL_ERROR")
    
    @staticmethod
    def cors_headers() -> Dict[str, str]:
        """CORS headers для всех ответов"""
        return {
            "Access-Control-Allow-Origin": "*",
            "Content-Type": "application/json"
        }


# ============ OPTIONS Handler ============

def handle_options() -> Tuple[str, int, Dict[str, str]]:
    """Обработка CORS preflight (OPTIONS)"""
    return '', 200, {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }


# ============ Authentication Wrapper ============

class AuthContext:
    """Контекст аутентификации (заполняется после authenticate_request)"""
    def __init__(self, account_id: int, auth_type: str, is_admin: bool = False):
        self.account_id = account_id  # Internal account_id (int)
        self.auth_type = auth_type    # "telegram" or "web"
        self.is_admin = is_admin


def authenticate_and_check(require_admin: bool = False) -> Optional[AuthContext]:
    """
    Единая функция аутентификации для всех API endpoints.
    Возвращает AuthContext или None если ошибка.
    
    Args:
        require_admin: Если True, проверяет что пользователь админ
    
    Returns:
        AuthContext с account_id и auth_type, или None если не авторизован
    """
    account_id = _authenticate_request()
    if not account_id:
        return None
    
    if require_admin:
        if not check_admin_access(account_id):
            return None  # Будет обработано в декораторе/роуте
    
    # Определяем тип авторизации
    auth_type = "unknown"
    web_token = request.headers.get('Authorization')
    if web_token and web_token.startswith('Bearer '):
        auth_type = "web"
    else:
        init_data = request.args.get('initData')
        if not init_data and request.is_json:
            try:
                data = request.get_json(silent=True)
                init_data = data.get('initData') if data else None
            except:
                pass
        if init_data:
            auth_type = "telegram"
    
    is_admin = check_admin_access(account_id)
    return AuthContext(account_id, auth_type, is_admin)


# ============ Decorators for Endpoints ============

def require_auth(func: Callable) -> Callable:
    """
    Декоратор: требует аутентификацию, возвращает AuthContext как первый параметр
    
    Использование:
        @require_auth
        def api_endpoint(auth: AuthContext):
            return APIResponse.success(account_id=auth.account_id)
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if request.method == 'OPTIONS':
            return handle_options()
        
        auth = authenticate_and_check(require_admin=False)
        if not auth:
            return APIResponse.unauthorized("Invalid or missing authentication")
        
        try:
            return func(auth, *args, **kwargs)
        except Exception as e:
            logger.error(f"Ошибка в {func.__name__}: {e}", exc_info=True)
            return APIResponse.internal_error()
    
    return wrapper


def require_admin(func: Callable) -> Callable:
    """
    Декоратор: требует админ права
    
    Использование:
        @require_admin
        def api_admin_endpoint(auth: AuthContext):
            return APIResponse.success()
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if request.method == 'OPTIONS':
            return handle_options()
        
        auth = authenticate_and_check(require_admin=True)
        if not auth:
            return APIResponse.unauthorized("Invalid or missing authentication")
        
        if not auth.is_admin:
            return APIResponse.forbidden("Admin access required")
        
        try:
            return func(auth, *args, **kwargs)
        except Exception as e:
            logger.error(f"Ошибка в {func.__name__}: {e}", exc_info=True)
            return APIResponse.internal_error()
    
    return wrapper


# ============ Helper: Run in Event Loop ============

def run_async(coro):
    """Запускает async корутину в новом event loop (для веб-роутов)"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ============ Export ============

__all__ = [
    "APIResponse",
    "AuthContext",
    "handle_options",
    "authenticate_and_check",
    "require_auth",
    "require_admin",
    "run_async",
]
