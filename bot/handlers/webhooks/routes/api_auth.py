"""
Blueprint: /api/auth/register, /api/auth/login, /api/auth/verify.
"""
import asyncio
import logging
import secrets
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint('api_auth', __name__)

    @bp.route('/api/auth/register', methods=['POST', 'OPTIONS'])
    def api_auth_register():
        """Регистрация нового веб-пользователя"""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            data = request.get_json(silent=True) or {}
            username = data.get('username', '').strip().lower()
            password = data.get('password', '')

            if not username or not password:
                return jsonify({'error': 'Логин и пароль обязательны'}), 400

            if len(username) < 3:
                return jsonify({'error': 'Логин слишком короткий'}), 400
            if len(password) < 6:
                return jsonify({'error': 'Пароль слишком короткий (минимум 6 символов)'}), 400

            password_hash = generate_password_hash(password)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                from ....db.accounts_db import (
                    get_or_create_account_for_username,
                    set_account_password,
                    set_account_auth_token,
                    username_available,
                )
                if not loop.run_until_complete(username_available(username, exclude_account_id=None)):
                    return jsonify({'error': 'Этот логин уже занят'}), 409
                account_id = loop.run_until_complete(get_or_create_account_for_username(username))
                loop.run_until_complete(set_account_password(account_id, password_hash))
                token = secrets.token_hex(32)
                loop.run_until_complete(set_account_auth_token(account_id, token))
                return jsonify({'success': True, 'token': token, 'account_id': account_id})
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Ошибка регистрации: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/auth/login', methods=['POST', 'OPTIONS'])
    def api_auth_login():
        """Вход веб-пользователя"""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            data = request.get_json(silent=True) or {}
            username = data.get('username', '').strip().lower()
            password = data.get('password', '')

            if not username or not password:
                return jsonify({'error': 'Введите логин и пароль'}), 400

            from ....db.accounts_db import (
                get_account_id_by_identity,
                get_account_password_hash,
                set_account_auth_token,
                get_username_for_account,
            )
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                account_id = loop.run_until_complete(get_account_id_by_identity("password", username))
                if not account_id:
                    return jsonify({'error': 'Неверный логин или пароль'}), 401
                pwd_hash = loop.run_until_complete(get_account_password_hash(account_id))
                if not pwd_hash or not check_password_hash(pwd_hash, password):
                    return jsonify({'error': 'Неверный логин или пароль'}), 401
                token = secrets.token_hex(32)
                loop.run_until_complete(set_account_auth_token(account_id, token))
                display_username = loop.run_until_complete(get_username_for_account(account_id)) or username
                return jsonify({
                    'success': True,
                    'token': token,
                    'account_id': account_id,
                    'username': display_username,
                })
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Ошибка входа: {e}")
            return jsonify({'error': str(e)}), 500

    @bp.route('/api/auth/verify', methods=['POST', 'OPTIONS'])
    def api_auth_verify():
        """Проверка токена (автоматический вход)"""
        if request.method == 'OPTIONS':
            return ('', 200, {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Allow-Headers": "*"})
        try:
            data = request.get_json(silent=True) or {}
            token = data.get('token')
            if not token:
                return jsonify({'error': 'Token required'}), 400

            from ....db.accounts_db import get_account_id_by_auth_token, get_username_for_account
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                account_id = loop.run_until_complete(get_account_id_by_auth_token(token))
                if not account_id:
                    return jsonify({'error': 'Invalid token'}), 401
                username = loop.run_until_complete(get_username_for_account(account_id))
                return jsonify({
                    'success': True,
                    'account_id': account_id,
                    'username': username,
                })
            finally:
                loop.close()
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return bp
