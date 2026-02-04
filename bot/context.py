"""
Единый контекст приложения (Фаза 2). Все глобальные сервисы и настройки в одном месте.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from telegram.ext import Application


@dataclass
class AppContext:
    """
    Контейнер сервисов и настроек. Создаётся в bot.py, передаётся в webhook app и startup.
    При режиме Remnawave subscription_manager и sync_manager могут быть None.
    """
    server_manager: Any
    subscription_manager: Optional[Any] = None  # None при Remnawave
    sync_manager: Optional[Any] = None  # None при Remnawave
    notification_manager: Optional[Any] = None
    admin_ids: List[int] = None
    telegram_app: Optional["Application"] = None
    config: Any = None  # bot.config module

    def __post_init__(self):
        if self.admin_ids is None:
            self.admin_ids = []


def get_app_context() -> Optional[AppContext]:
    """
    Возвращает текущий AppContext: из Flask current_app или из модуля bot.bot.
    """
    try:
        from flask import current_app
        ctx = current_app.config.get("BOT_CONTEXT")
        if ctx is not None:
            return ctx
    except RuntimeError:
        pass  # вне контекста Flask (например, Telegram handler)
    try:
        import sys
        bot_module = sys.modules.get("bot.bot")
        if bot_module is not None:
            return getattr(bot_module, "app_context", None)
    except (ImportError, AttributeError):
        pass
    return None
