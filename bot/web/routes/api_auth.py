"""
Quart Blueprint: /api/auth/register, /api/auth/login, /api/auth/verify, /api/auth/logout.
Cookie daralla_web_token для PWA (persist в standalone), токен в теле/заголовке по-прежнему поддерживается.
Для общего входа на daralla.ru и app.daralla.ru задайте AUTH_COOKIE_DOMAIN=.daralla.ru
"""
import logging
import os
import secrets

from quart import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

from bot.db.users_db import (
    register_web_user,
    get_user_by_username_or_id,
    update_user_auth_token,
    get_user_by_auth_token,
)

logger = logging.getLogger(__name__)

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "*",
}

AUTH_COOKIE_NAME = "daralla_web_token"
AUTH_COOKIE_MAX_AGE_REMEMBER = 30 * 24 * 3600  # 30 дней
# Общий домен для cookie: один вход на daralla.ru и app.daralla.ru (PWA/мини-апп)
AUTH_COOKIE_DOMAIN = os.environ.get("AUTH_COOKIE_DOMAIN", "").strip() or None  # например ".daralla.ru"


def create_blueprint(bot_app):
    bp = Blueprint("api_auth", __name__)

    @bp.route("/api/auth/register", methods=["POST", "OPTIONS"])
    async def api_auth_register():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            data = await request.get_json(silent=True) or {}
            username = (data.get("username") or "").strip().lower()
            password = (data.get("password") or "").strip()

            if not username or not password:
                return jsonify({"error": "Логин и пароль обязательны"}), 400
            if len(username) < 3:
                return jsonify({"error": "Логин слишком короткий"}), 400
            if len(password) < 6:
                return jsonify({"error": "Пароль слишком короткий (минимум 6 символов)"}), 400

            password_hash = generate_password_hash(password)
            user_id = await register_web_user(username, password_hash)
            token = secrets.token_hex(32)
            await update_user_auth_token(user_id, token)
            resp = jsonify({"success": True, "token": token, "user_id": user_id})
            _set_auth_cookie(resp, token, remember=True)
            return resp
        except Exception as e:
            logger.error("Ошибка регистрации: %s", e)
            return jsonify({"error": str(e)}), 500

    @bp.route("/api/auth/login", methods=["POST", "OPTIONS"])
    async def api_auth_login():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            data = await request.get_json(silent=True) or {}
            username = (data.get("username") or "").strip().lower()
            password = (data.get("password") or "").strip()

            if not username or not password:
                return jsonify({"error": "Введите логин и пароль"}), 400

            user = await get_user_by_username_or_id(username)
            if not user or not user.get("password_hash") or not check_password_hash(
                user["password_hash"], password
            ):
                return jsonify({"error": "Неверный логин или пароль"}), 401

            token = secrets.token_hex(32)
            await update_user_auth_token(user["user_id"], token)
            remember = data.get("remember", True)
            resp = jsonify({
                "success": True,
                "token": token,
                "user_id": user["user_id"],
                "username": user.get("username") or user["user_id"],
            })
            _set_auth_cookie(resp, token, remember=remember)
            return resp
        except Exception as e:
            logger.error("Ошибка входа: %s", e)
            return jsonify({"error": str(e)}), 500

    @bp.route("/api/auth/verify", methods=["POST", "OPTIONS"])
    async def api_auth_verify():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            data = await request.get_json(silent=True) or {}
            token = data.get("token") or request.cookies.get(AUTH_COOKIE_NAME)
            if not token:
                return jsonify({"error": "Token required"}), 400

            user = await get_user_by_auth_token(token)
            if not user:
                return jsonify({"error": "Invalid token"}), 401
            return jsonify({
                "success": True,
                "user_id": user["user_id"],
                "username": user.get("username"),
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @bp.route("/api/auth/logout", methods=["POST", "OPTIONS"])
    async def api_auth_logout():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        resp = jsonify({"success": True})
        _clear_auth_cookie(resp)
        return resp

    return bp


def _set_auth_cookie(response, token, *, remember=True):
    secure = getattr(request, "is_secure", None)
    if secure is None and hasattr(request, "url"):
        secure = (request.url or "").startswith("https://")
    if secure is None:
        secure = True
    max_age = AUTH_COOKIE_MAX_AGE_REMEMBER if remember else None
    kwargs = {
        "key": AUTH_COOKIE_NAME,
        "value": token,
        "max_age": max_age,
        "httponly": True,
        "samesite": "Lax",
        "path": "/",
        "secure": secure,
    }
    if AUTH_COOKIE_DOMAIN:
        kwargs["domain"] = AUTH_COOKIE_DOMAIN
    response.set_cookie(**kwargs)


def _clear_auth_cookie(response):
    kwargs = {"key": AUTH_COOKIE_NAME, "path": "/"}
    if AUTH_COOKIE_DOMAIN:
        kwargs["domain"] = AUTH_COOKIE_DOMAIN
    response.delete_cookie(**kwargs)
