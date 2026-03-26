"""
Единый контейнер зависимостей приложения.
Заменяет sys.modules хаки: все сервисы и конфигурация доступны через get_ctx().
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .services.subscription_manager import SubscriptionManager
    from .services.notification_manager import NotificationManager
    from .services.remnawave_service import RemnaWaveService

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    subscription_manager: SubscriptionManager | None = None
    notification_manager: NotificationManager | None = None
    remnawave_service: RemnaWaveService | None = None
    admin_ids: list[int] = field(default_factory=list)
    webapp_url: str | None = None
    vpn_brand_name: str = "Daralla VPN"


_ctx: AppContext | None = None


def get_ctx() -> AppContext:
    """Возвращает глобальный AppContext. Вызывать только после set_ctx()."""
    if _ctx is None:
        raise RuntimeError("AppContext не инициализирован. Вызовите set_ctx() при старте.")
    return _ctx


def set_ctx(ctx: AppContext) -> None:
    """Устанавливает глобальный AppContext (вызывается один раз при старте приложения)."""
    global _ctx
    _ctx = ctx
    logger.info("AppContext установлен")
