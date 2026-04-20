"""Service wrappers for user account operations used by HTTP routes."""

from __future__ import annotations

from bot.db.users_db import (
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
