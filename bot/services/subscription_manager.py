"""Упрощенный менеджер подписок для RemnaWave-only runtime."""

import datetime
import logging
from typing import Optional, Tuple

from ..db.subscriptions_db import (
    create_subscription,
    get_all_active_subscriptions_by_user,
    get_subscription_by_id_only,
)
from ..db.users_db import get_or_create_subscriber
from .remnawave_service import RemnaWaveService

logger = logging.getLogger(__name__)


class SubscriptionManager:
    """Высокоуровневый менеджер подписок на базе RemnaWaveService."""

    def __init__(self, remnawave_service: RemnaWaveService):
        self.remnawave_service = remnawave_service

    async def create_subscription_for_user(
        self,
        user_id: str,
        period: str,
        device_limit: int,
        price: float,
        name: str | None = None,
        expires_at: int | None = None,
    ) -> Tuple[dict, str]:
        """Создаёт подписку в локальной БД и синхронизирует runtime в RemnaWave."""

        subscriber_id = await get_or_create_subscriber(user_id)

        if expires_at is None:
            days = 90 if period == "3month" else 30
            now = int(datetime.datetime.now().timestamp())
            expires_at = now + days * 24 * 60 * 60

        if not name:
            existing_subs = await get_all_active_subscriptions_by_user(user_id)
            subscription_number = len(existing_subs) + 1
            name = f"Подписка {subscription_number}"

        subscription_id, token = await create_subscription(
            subscriber_id=subscriber_id,
            period=period,
            device_limit=device_limit,
            price=price,
            expires_at=expires_at,
            name=name,
        )

        sub_dict = await get_subscription_by_id_only(subscription_id)
        await self.remnawave_service.ensure_active_access(
            subscription_id=subscription_id,
            user_id=str(user_id),
            token=token,
            expires_at=expires_at,
            device_limit=device_limit,
        )
        logger.info("Подписка создана в remna-runtime: subscription_id=%s", subscription_id)
        return sub_dict, token


    async def ensure_access(
        self,
        subscription_id: int,
        user_id: str,
        expires_at: int,
        token: str,
        device_limit: int | None = None,
    ) -> bool:
        device_limit = int(device_limit or 1)
        return await self.remnawave_service.ensure_active_access(
            subscription_id=subscription_id,
            user_id=str(user_id),
            token=token,
            expires_at=expires_at,
            device_limit=device_limit,
        )

    async def suspend_access(self, subscription_id: int) -> bool:
        return await self.remnawave_service.suspend_access(subscription_id=subscription_id)

    async def get_subscription_link(self, subscription_id: int) -> str | None:
        sub_record = await get_subscription_by_id_only(subscription_id)
        if not sub_record:
            return None
        return await self.remnawave_service.get_subscription_link(
            subscription_id=subscription_id,
            token=sub_record["subscription_token"],
        )

    async def ensure_client_on_server(
        self,
        subscription_id: int,
        server_name: str,
        client_email: str,
        user_id: str,
        expires_at: int,
        token: str,
        device_limit: int = None,
        panel_entry: Optional[dict] = None,
    ) -> Tuple[bool, bool]:
        """Deprecated compatibility wrapper for old call sites."""
        _ = (server_name, client_email, panel_entry)
        ok = await self.ensure_access(
            subscription_id=subscription_id,
            user_id=user_id,
            expires_at=expires_at,
            token=token,
            device_limit=device_limit,
        )
        return ok, ok

    async def attach_server_to_subscription(
        self,
        subscription_id: int,
        server_name: str,
        client_email: str,
        client_id: Optional[str] = None,
    ) -> int:
        """Deprecated compatibility no-op in RemnaWave-only runtime."""
        _ = (subscription_id, server_name, client_email, client_id)
        return 0

