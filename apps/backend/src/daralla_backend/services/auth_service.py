"""Service layer for web auth routes."""

from __future__ import annotations

import secrets

import aiosqlite
from werkzeug.security import check_password_hash

from bot.db.users_db import (
    UsernameAlreadyExistsError,
    get_user_by_auth_token,
    get_user_by_username_or_id,
    register_web_user,
    update_user_auth_token,
)


class AuthServiceError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def register_user_and_issue_token(username: str, password_hash: str):
    try:
        user_id = await register_web_user(username, password_hash)
        token = secrets.token_hex(32)
        await update_user_auth_token(user_id, token)
        return {"token": token, "user_id": user_id}
    except UsernameAlreadyExistsError:
        raise AuthServiceError("Пользователь с таким логином уже существует", 409)
    except aiosqlite.IntegrityError:
        raise AuthServiceError("Пользователь с таким логином уже существует", 409)
    except aiosqlite.Error:
        raise AuthServiceError("Database error", 500)


async def login_user_and_issue_token(username: str, password: str):
    try:
        user = await get_user_by_username_or_id(username)
        if not user or not user.get("password_hash") or not check_password_hash(user["password_hash"], password):
            raise AuthServiceError("Неверный логин или пароль", 401)
        token = secrets.token_hex(32)
        await update_user_auth_token(user["user_id"], token)
        return {
            "token": token,
            "user_id": user["user_id"],
            "username": user.get("username") or user["user_id"],
        }
    except AuthServiceError:
        raise
    except aiosqlite.Error:
        raise AuthServiceError("Database error", 500)


async def verify_auth_token(token: str):
    try:
        return await get_user_by_auth_token(token)
    except aiosqlite.Error:
        raise AuthServiceError("Database error", 500)
