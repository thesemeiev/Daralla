"""
Модуль событий (реферальные конкурсы с рейтингом и наградами).
Модуль включён по умолчанию. Отключение: EVENTS_MODULE_ENABLED=false
"""

from .config import EVENTS_MODULE_ENABLED

# Хук успешной оплаты: вызывать из payment_processors после успешной покупки/продления
async def on_payment_success(account_id: str) -> None:
    from .payment_hook import on_payment_success as _impl
    await _impl(account_id)

__all__ = ["EVENTS_MODULE_ENABLED", "on_payment_success"]
