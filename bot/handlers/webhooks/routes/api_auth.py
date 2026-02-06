"""
Blueprint: /api/auth/register, /api/auth/login, /api/auth/verify.
"""
import logging
import secrets
from typing import Tuple, Dict, Any, Union
from flask import Blueprint, request, Response
from werkzeug.security import generate_password_hash, check_password_hash

from ..webhook_utils import APIResponse, require_auth, run_async, handle_options

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint('api_auth', __name__)

    @bp.route('/api/auth/register', methods=['POST', 'OPTIONS'])
    def api_auth_register() -> Union[Tuple[Response, int, Dict], Tuple[str, int, Dict[str, str]]]:
        """Регистрация нового веб-пользователя"""
        if request.method == 'OPTIONS':
            return handle_options()
        
        try:
            data = request.get_json(silent=True) or {}
            username = (data.get('username') or '').strip().lower()
            password = data.get('password') or ''

            if not username or not password:
                return APIResponse.bad_request('Username and password are required')

            if len(username) < 3:
                return APIResponse.bad_request('Username too short (min 3 characters)')
            if len(password) < 6:
                return APIResponse.bad_request('Password too short (min 6 characters)')

            password_hash = generate_password_hash(password)

            async def register():
                from ....db.accounts_db import (
                    get_or_create_account_for_username,
                    set_account_password,
                    set_account_auth_token,
                    username_available,
                )
                if not await username_available(username, exclude_account_id=None):
                    return APIResponse.conflict('Username already taken')
                account_id = await get_or_create_account_for_username(username)
                await set_account_password(account_id, password_hash)
                token = secrets.token_hex(32)
                await set_account_auth_token(account_id, token)
                return APIResponse.success(token=token, account_id=account_id)

            result = run_async(register())
            return result
        except Exception as e:
            logger.error(f"Registration error: {e}", exc_info=True)
            return APIResponse.internal_error()

    @bp.route('/api/auth/login', methods=['POST', 'OPTIONS'])
    def api_auth_login() -> Union[Tuple[Response, int, Dict], Tuple[str, int, Dict[str, str]]]:
        """Вход веб-пользователя"""
        if request.method == 'OPTIONS':
            return handle_options()
        
        try:
            data = request.get_json(silent=True) or {}
            username = (data.get('username') or '').strip().lower()
            password = data.get('password') or ''

            if not username or not password:
                return APIResponse.bad_request('Username and password required')

            async def login():
                from ....db.accounts_db import (
                    get_account_id_by_identity,
                    get_account_password_hash,
                    set_account_auth_token,
                    get_username_for_account,
                )
                account_id = await get_account_id_by_identity("password", username)
                if not account_id:
                    return APIResponse.unauthorized('Invalid username or password')
                
                pwd_hash = await get_account_password_hash(account_id)
                if not pwd_hash or not check_password_hash(pwd_hash, password):
                    return APIResponse.unauthorized('Invalid username or password')
                
                token = secrets.token_hex(32)
                await set_account_auth_token(account_id, token)
                display_username = await get_username_for_account(account_id) or username
                
                return APIResponse.success(
                    token=token,
                    account_id=account_id,
                    username=display_username,
                )

            result = run_async(login())
            return result
        except Exception as e:
            logger.error(f"Login error: {e}", exc_info=True)
            return APIResponse.internal_error()

    @bp.route('/api/auth/verify', methods=['POST', 'OPTIONS'])
    def api_auth_verify() -> Union[Tuple[Response, int, Dict], Tuple[str, int, Dict[str, str]]]:
        """Проверка токена (автоматический вход)"""
        if request.method == 'OPTIONS':
            return handle_options()
        
        try:
            data = request.get_json(silent=True) or {}
            token = data.get('token')
            if not token:
                return APIResponse.bad_request('Token required')

            async def verify():
                from ....db.accounts_db import get_account_id_by_auth_token, get_username_for_account
                account_id = await get_account_id_by_auth_token(token)
                if not account_id:
                    return APIResponse.unauthorized('Invalid token')
                
                username = await get_username_for_account(account_id)
                return APIResponse.success(
                    account_id=account_id,
                    username=username,
                )

            result = run_async(verify())
            return result
        except Exception as e:
            logger.error(f"Token verify error: {e}", exc_info=True)
            return APIResponse.internal_error()

    return bp
