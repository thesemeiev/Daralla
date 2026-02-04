"""
Менеджер подписок. В режиме Remnawave подписки управляются через Remnawave;
локальное создание/синхронизация с X-UI не используются.
"""

import logging
from typing import Optional, Tuple

from .server_manager import MultiServerManager

logger = logging.getLogger(__name__)


class SubscriptionManager:
    """
    Заглушка для совместимости с кодом, ожидающим SubscriptionManager.
    В Remnawave подписки и доступ выдаются через панель Remnawave.
    """

    def __init__(self, server_manager: MultiServerManager):
        self.server_manager = server_manager

    async def create_subscription_for_user(
        self,
        user_id: str,
        period: str,
        device_limit: int,
        price: float,
        name: str | None = None,
        group_id: int | None = None,
        expires_at: int | None = None,
    ) -> Tuple[dict, str]:
        raise RuntimeError("Remnawave-only: создание подписок через БД отключено")

    async def attach_server_to_subscription(
        self,
        subscription_id: int,
        server_name: str,
        client_email: str,
        client_id: Optional[str] = None,
    ) -> int:
        raise RuntimeError("Remnawave-only: привязка серверов к подписке отключена")

    async def ensure_client_on_server(
        self,
        subscription_id: int,
        server_name: str,
        client_email: str,
        user_id: str,
        expires_at: int,
        token: str,
        device_limit: int = None,
    ) -> Tuple[bool, bool]:
        return False, False

    async def sync_servers_with_config(self, auto_create_clients: bool = True) -> dict:
        return {
            "subscriptions_checked": 0,
            "servers_added": 0,
            "servers_removed": 0,
            "clients_created": 0,
            "clients_restored": 0,
            "errors": [],
        }
