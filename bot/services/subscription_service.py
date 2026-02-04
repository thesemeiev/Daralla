"""
Единый сервис подписок. Источник истины — Remnawave.
Вся логика Remnawave API (создание/продление пользователя) сосредоточена здесь.
"""
from __future__ import annotations

import datetime
import logging
import time
from typing import Any, Optional, Tuple

from ..db.accounts_db import (
    get_remnawave_mapping,
    set_remnawave_mapping,
    get_telegram_id_for_account,
    get_username_for_account,
    upsert_account_expiry_cache,
)

logger = logging.getLogger(__name__)


def _get_client():
    from .remnawave_service import RemnawaveClient, load_remnawave_config
    cfg = load_remnawave_config()
    return RemnawaveClient(cfg)


async def get_subscriptions_for_account(account_id: int) -> list[dict[str, Any]]:
    """Список подписок аккаунта из Remnawave (обычно одна запись)."""
    mapping = await get_remnawave_mapping(account_id)
    if not mapping:
        return []
    short_uuid = mapping.get("remnawave_short_uuid")
    if not short_uuid:
        return []
    try:
        client = _get_client()
        info = client.get_sub_info(short_uuid)
        obj = info.get("obj") or info.get("data") or info
        exp_ms = obj.get("expiresAt") or obj.get("expires_at") or obj.get("expiryTime") or 0
        exp_ts = int(exp_ms / 1000) if exp_ms and exp_ms >= 1e12 else (int(exp_ms) if exp_ms else 0)
        current_time = int(time.time())
        is_active = exp_ts > current_time if exp_ts else False
        return [{
            "id": 0,
            "name": "Подписка",
            "status": "active" if is_active else "expired",
            "period": "month",
            "device_limit": obj.get("deviceLimit", 1),
            "created_at": current_time,
            "created_at_formatted": datetime.datetime.now().strftime("%d.%m.%Y %H:%M"),
            "expires_at": exp_ts,
            "expires_at_formatted": datetime.datetime.fromtimestamp(exp_ts).strftime("%d.%m.%Y %H:%M") if exp_ts else "—",
            "price": 0,
            "token": short_uuid,
            "short_uuid": short_uuid,
            "days_remaining": max(0, (exp_ts - current_time) // (24 * 60 * 60)) if is_active and exp_ts else 0,
        }]
    except Exception as e:
        logger.warning("Remnawave get_sub_info for account %s: %s", account_id, e)
        return []


async def extend_subscription(account_id: int, add_days: int, device_limit: Optional[int] = None) -> Optional[int]:
    """
    Продлевает подписку в Remnawave на add_days дней.
    Возвращает новый expires_at (unix seconds) или None.
    """
    mapping = await get_remnawave_mapping(account_id)
    if not mapping:
        return None
    uuid_rw = mapping.get("remnawave_user_uuid")
    short_uuid = mapping.get("remnawave_short_uuid")
    if not uuid_rw or not short_uuid:
        return None
    try:
        client = _get_client()
        new_expiry = client.extend_user_by_days(uuid_rw, short_uuid, add_days, device_limit=device_limit)
        await upsert_account_expiry_cache(account_id, new_expiry)
        return new_expiry
    except Exception as e:
        logger.error("Remnawave extend for account %s: %s", account_id, e)
        return None


async def set_subscription_expiry(account_id: int, expires_at_unix: int, device_limit: Optional[int] = None) -> bool:
    """Устанавливает срок подписки в Remnawave."""
    mapping = await get_remnawave_mapping(account_id)
    if not mapping:
        return False
    uuid_rw = mapping.get("remnawave_user_uuid")
    if not uuid_rw:
        return False
    try:
        client = _get_client()
        client.update_user_expiry(uuid_rw, expires_at_unix, device_limit=device_limit)
        await upsert_account_expiry_cache(account_id, expires_at_unix)
        return True
    except Exception as e:
        logger.error("Remnawave update_user_expiry for account %s: %s", account_id, e)
        return False


async def activate_subscription_after_payment(
    account_id: int,
    days: int,
    device_limit: int = 1,
    is_extension: bool = False,
) -> Tuple[bool, Optional[str], Optional[int], Optional[str]]:
    """
    Активация/продление подписки после успешной оплаты.
    Создаёт пользователя в Remnawave при отсутствии маппинга, продлевает или выставляет срок.
    Возвращает (success, short_uuid, new_expires_at, error_message).
    """
    from .remnawave_service import RemnawaveError

    try:
        client = _get_client()
    except Exception as e:
        logger.error("Remnawave config failed: %s", e)
        return False, None, None, str(e)

    mapping = await get_remnawave_mapping(account_id)
    if not mapping:
        telegram_id = await get_telegram_id_for_account(account_id)
        username = await get_username_for_account(account_id)
        try:
            remna_user = None
            if telegram_id:
                remna_user = client.get_user_by_telegram_id(telegram_id)
            if not remna_user and username:
                remna_user = client.get_user_by_username(username)
            if not remna_user:
                now_ts = int(time.time())
                exp_ts = now_ts + days * 24 * 60 * 60
                expire_at_iso = datetime.datetime.utcfromtimestamp(exp_ts).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                create_payload = {
                    "username": (username or f"acc_{account_id}").strip() or f"acc_{account_id}",
                    "expireAt": expire_at_iso,
                }
                if telegram_id:
                    create_payload["telegramId"] = int(telegram_id)
                created = client.create_user(create_payload)
                ruuid = created.get("uuid") or created.get("id")
                short_uuid = created.get("shortUuid") or created.get("short_uuid") or created.get("shortId")
                if ruuid:
                    await set_remnawave_mapping(account_id, str(ruuid), short_uuid or None)
                    mapping = await get_remnawave_mapping(account_id)
                else:
                    logger.warning(
                        "Remnawave create_user response missing uuid; keys=%s",
                        list(created.keys()) if isinstance(created, dict) else type(created).__name__,
                    )
            else:
                ruuid = remna_user.get("uuid") or remna_user.get("id")
                short_uuid = remna_user.get("shortUuid") or remna_user.get("short_uuid")
                if ruuid:
                    await set_remnawave_mapping(account_id, str(ruuid), short_uuid)
                    mapping = await get_remnawave_mapping(account_id)
        except RemnawaveError as e:
            logger.error("Remnawave create/lookup failed: %s", e)
            return False, None, None, str(e)

    if not mapping:
        logger.error("No Remnawave mapping for account_id=%s after ensure", account_id)
        return False, None, None, "No mapping"

    uuid_rw = mapping.get("remnawave_user_uuid")
    short_uuid = mapping.get("remnawave_short_uuid")
    if not uuid_rw:
        return False, None, None, "No remnawave_user_uuid"

    try:
        if is_extension and short_uuid:
            new_expires_at = client.extend_user_by_days(uuid_rw, short_uuid, days, device_limit=device_limit)
        else:
            now_ts = int(time.time())
            new_expires_at = now_ts + days * 24 * 60 * 60
            client.update_user_expiry(uuid_rw, new_expires_at, device_limit=device_limit)
        await upsert_account_expiry_cache(account_id, new_expires_at)
        return True, short_uuid, new_expires_at, None
    except RemnawaveError as e:
        logger.error("Remnawave extend/update failed: %s", e)
        return False, None, None, str(e)
