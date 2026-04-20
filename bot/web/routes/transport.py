"""Shared transport-layer helpers for route handlers."""

from __future__ import annotations

from quart import jsonify


def error_response(message: str, status_code: int = 400):
    return jsonify({"error": message}), status_code


def service_error_response(exc):
    message = getattr(exc, "message", str(exc))
    status_code = getattr(exc, "status_code", 500)
    return jsonify({"error": message}), status_code


def auth_error_payload(status_code: int):
    if status_code == 401:
        return error_response("Unauthorized", 401)
    if status_code == 403:
        return error_response("Access denied", 403)
    return error_response("Authentication error", status_code)
