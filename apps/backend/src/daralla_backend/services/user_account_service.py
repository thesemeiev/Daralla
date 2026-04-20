"""Service wrappers for user account operations used by HTTP routes."""

from __future__ import annotations

import requests as requests_lib
from werkzeug.security import check_password_hash, generate_password_hash

from daralla_backend.handlers.api_support.webhook_auth import verify_telegram_init_data
from daralla_backend.db.users_db import (
    create_telegram_link,
    delete_telegram_link,
    get_telegram_chat_id_for_notification,
    get_user_by_id,
    get_user_by_telegram_id_v2,
    link_telegram_create_state,
    mark_telegram_id_known,
    rename_user_id,
    update_user_password,
    update_user_telegram_id,
    update_user_username,
    username_available,
)


class UserAccountServiceError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class UserAvatarServiceError(Exception):
    def __init__(self, status_code: int):
        super().__init__(f"avatar_error_{status_code}")
        self.status_code = status_code


async def fetch_user_by_telegram_id(telegram_id: str):
    return await get_user_by_telegram_id_v2(telegram_id, use_fallback=True)


async def fetch_user_by_id(user_id: str):
    return await get_user_by_id(user_id)


async def is_username_available_for_user(username: str, user_id: str) -> bool:
    return await username_available(username, user_id)


async def update_user_credentials(user_id: str, username: str, password_hash: str) -> None:
    await update_user_username(user_id, username)
    await update_user_password(user_id, password_hash)


async def update_password(user_id: str, password_hash: str) -> None:
    await update_user_password(user_id, password_hash)


async def update_username(user_id: str, username: str) -> None:
    await update_user_username(user_id, username)


async def create_link_state_for_user(user_id: str) -> str:
    return await link_telegram_create_state(user_id)


async def get_notification_chat_id(user_id: str):
    return await get_telegram_chat_id_for_notification(user_id)


async def unlink_telegram_id(user_id: str, telegram_id: str) -> None:
    await delete_telegram_link(telegram_id)
    await mark_telegram_id_known(telegram_id)
    await update_user_telegram_id(user_id, None)


async def convert_legacy_user_to_web(user_id: str, username: str) -> str:
    new_user_id = f"web_{username}"
    await rename_user_id(user_id, new_user_id)
    return new_user_id


async def create_telegram_binding(telegram_id: str, user_id: str) -> None:
    await create_telegram_link(telegram_id, user_id)
    await update_user_telegram_id(user_id, telegram_id)


async def change_password_for_user(user_id: str, current_password: str, new_password: str) -> None:
    user = await fetch_user_by_id(user_id)
    if not user or not user.get("password_hash"):
        raise UserAccountServiceError("Пароль для этого аккаунта не настроен", 400)
    if not check_password_hash(user["password_hash"], current_password):
        raise UserAccountServiceError("Неверный текущий пароль", 401)
    if check_password_hash(user["password_hash"], new_password):
        raise UserAccountServiceError("Новый пароль должен отличаться от текущего", 400)
    await update_password(user_id, generate_password_hash(new_password))


async def change_login_for_user(user_id: str, current_password: str, new_login: str) -> None:
    user = await fetch_user_by_id(user_id)
    if not user or not user.get("password_hash"):
        raise UserAccountServiceError("Пароль для этого аккаунта не настроен", 400)
    if not check_password_hash(user["password_hash"], current_password):
        raise UserAccountServiceError("Неверный текущий пароль", 401)
    current_username = (user.get("username") or "").strip().lower()
    if new_login == current_username:
        raise UserAccountServiceError("Укажите новый логин, отличный от текущего", 400)
    is_available = await is_username_available_for_user(new_login, user_id)
    if not is_available:
        raise UserAccountServiceError("Этот логин уже занят", 409)
    await update_username(user_id, new_login)


async def unlink_telegram_for_user(user_id: str, current_password: str):
    user = await fetch_user_by_id(user_id)
    if not user:
        raise UserAccountServiceError("Пользователь не найден", 404)
    if not user.get("password_hash"):
        raise UserAccountServiceError(
            "Для отвязки Telegram необходимо сначала настроить веб-доступ (логин и пароль)",
            400,
        )
    if not check_password_hash(user["password_hash"], current_password):
        raise UserAccountServiceError("Неверный текущий пароль", 401)

    telegram_id = user.get("telegram_id")
    if telegram_id is not None:
        telegram_id = str(telegram_id)
    if not telegram_id:
        chat_id = await get_notification_chat_id(user_id)
        if chat_id is not None:
            telegram_id = str(chat_id)

    is_legacy_tg_format = user_id.startswith("tg_") or user_id.isdigit()
    if not telegram_id:
        raise UserAccountServiceError("Telegram не привязан к этому аккаунту", 400)
    if is_legacy_tg_format:
        username = user.get("username")
        if not username:
            raise UserAccountServiceError(
                "Ошибка: у аккаунта нет логина для превращения в веб-аккаунт. Сначала смените логин.",
                400,
            )
        new_user_id = await convert_legacy_user_to_web(user_id, username)
        user_id = new_user_id
    await unlink_telegram_id(user_id, telegram_id)
    return {"user_id": user_id, "telegram_id": telegram_id}


async def setup_web_access_for_telegram_user(init_data: str, username: str, password: str):
    telegram_id = verify_telegram_init_data(init_data)
    if not telegram_id:
        raise UserAccountServiceError("Invalid authentication", 401)

    user = await fetch_user_by_telegram_id(str(telegram_id))
    if not user:
        raise UserAccountServiceError("Пользователь не найден", 404)

    user_id = user["user_id"]
    is_available = await is_username_available_for_user(username, user_id)
    if not is_available:
        raise UserAccountServiceError("Этот логин уже занят", 409)

    password_hash = generate_password_hash(password)
    await update_user_credentials(user_id, username, password_hash)
    return {"username": username, "user_id": user_id}


async def load_user_avatar_bytes(user_id: str, telegram_token: str):
    if not telegram_token:
        raise UserAvatarServiceError(500)

    user = await fetch_user_by_id(user_id)
    if not user:
        raise UserAvatarServiceError(404)

    telegram_id = user.get("telegram_id")
    if not telegram_id:
        raise UserAvatarServiceError(404)

    base = f"https://api.telegram.org/bot{telegram_token}"
    photos_r = requests_lib.get(
        f"{base}/getUserProfilePhotos",
        params={"user_id": int(telegram_id), "limit": 1},
        timeout=10,
    )
    if not photos_r.ok:
        raise UserAvatarServiceError(502)

    data = photos_r.json()
    if not data.get("ok") or not data.get("result", {}).get("photos"):
        raise UserAvatarServiceError(404)

    file_id = data["result"]["photos"][0][-1]["file_id"]
    file_r = requests_lib.get(f"{base}/getFile", params={"file_id": file_id}, timeout=10)
    if not file_r.ok:
        raise UserAvatarServiceError(502)

    file_data = file_r.json()
    if not file_data.get("ok"):
        raise UserAvatarServiceError(404)

    file_path = file_data["result"].get("file_path")
    if not file_path:
        raise UserAvatarServiceError(404)

    image_r = requests_lib.get(f"https://api.telegram.org/file/bot{telegram_token}/{file_path}", timeout=10)
    if not image_r.ok:
        raise UserAvatarServiceError(502)
    return image_r.content
