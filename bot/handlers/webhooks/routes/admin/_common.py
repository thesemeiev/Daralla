"""
Общие хелперы для админ-маршрутов: CORS, проверка прав.
"""
from flask import request, jsonify

from ...webhook_auth import authenticate_request, check_admin_access

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "*",
}


def options_response():
    """Ответ на preflight OPTIONS."""
    return ("", 200, CORS_HEADERS)


def require_admin():
    """
    Проверяет аутентификацию и права админа.
    Возвращает (None, None) если ок, иначе (response, status_code).
    """
    user_id = authenticate_request()
    if not user_id:
        return jsonify({"error": "Invalid authentication"}), 401
    if not check_admin_access(user_id):
        return jsonify({"error": "Access denied"}), 403
    return None, None


def json_ok(data, status=200):
    """Ответ 200 JSON с CORS."""
    headers = {**CORS_HEADERS, "Content-Type": "application/json"}
    return jsonify(data), status, headers
