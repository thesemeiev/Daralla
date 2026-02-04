"""
Менеджер синхронизации данных между БД и серверами X-UI.
В режиме Remnawave синхронизация подписок не выполняется (источник истины — Remnawave).
"""
import logging
from typing import Dict, Any

from .subscription_manager import SubscriptionManager

logger = logging.getLogger(__name__)


def _remnawave_only_stats() -> Dict[str, Any]:
    return {
        "subscriptions_checked": 0,
        "subscriptions_synced": 0,
        "total_servers_checked": 0,
        "total_servers_synced": 0,
        "total_clients_created": 0,
        "total_errors": 0,
        "errors": [],
    }


class SyncManager:
    """Менеджер для поддержания консистентности данных (в Remnawave режиме — no-op)."""

    def __init__(self, server_manager, subscription_manager: SubscriptionManager):
        self.server_manager = server_manager
        self.subscription_manager = subscription_manager
        self.is_running = False

    async def sync_all_subscriptions(self, auto_fix: bool = False):
        """В режиме Remnawave не выполняется."""
        try:
            from ..services.remnawave_service import is_remnawave_configured
            if is_remnawave_configured():
                logger.info("Remnawave включён — sync_all_subscriptions пропущена")
                return _remnawave_only_stats()
        except Exception:
            pass
        return _remnawave_only_stats()

    async def run_sync(self):
        """В режиме Remnawave не выполняется."""
        try:
            from ..services.remnawave_service import is_remnawave_configured
            if is_remnawave_configured():
                logger.info("Remnawave включён — run_sync пропущена")
                return
        except Exception:
            pass
        logger.info("Режим без Remnawave не поддерживается — run_sync пропущена")

    async def cleanup_expired_subscriptions(self, days_limit: int = 3):
        """В режиме Remnawave не выполняется."""
        pass

    async def _get_subscription_by_id(self, sub_id: int):
        """В режиме Remnawave не используется."""
        return None

    async def sync_all_clients_states(self):
        """В режиме Remnawave не выполняется."""
        pass

    async def cleanup_orphaned_clients(self):
        """В режиме Remnawave не выполняется."""
        return {"deleted_count": 0, "servers_checked": 0, "errors": [], "details": []}
