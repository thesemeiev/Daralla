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

            from ....db.users_db import register_web_user
            password_hash = generate_password_hash(password)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                user_id = loop.run_until_complete(register_web_user(username, password_hash))
                token = secrets.token_hex(32)
                from ....db.users_db import update_user_auth_token
                loop.run_until_complete(update_user_auth_token(user_id, token))
                return jsonify({'success': True, 'token': token, 'user_id': user_id})
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

            from ....db.users_db import get_user_by_username_or_id
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                user = loop.run_until_complete(get_user_by_username_or_id(username))
                if not user or not user['password_hash'] or not check_password_hash(user['password_hash'], password):
                    return jsonify({'error': 'Неверный логин или пароль'}), 401

                token = secrets.token_hex(32)
                from ....db.users_db import update_user_auth_token
                loop.run_until_complete(update_user_auth_token(user['user_id'], token))
                return jsonify({
                    'success': True,
                    'token': token,
                    'user_id': user['user_id'],
                    'username': user['username'] or user['user_id']
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

            from ....db.users_db import get_user_by_auth_token
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                user = loop.run_until_complete(get_user_by_auth_token(token))
                if not user:
                    return jsonify({'error': 'Invalid token'}), 401
                return jsonify({
                    'success': True,
                    'user_id': user['user_id'],
                    'username': user['username']
                })
            finally:
                loop.close()
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return bp
