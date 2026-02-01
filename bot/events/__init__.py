"""
Модуль событий (реферальные конкурсы с рейтингом и наградами).
Подключаемый: отключение через EVENTS_MODULE_ENABLED=False или удаление папки.
"""

from .config import EVENTS_MODULE_ENABLED

# Хук успешной оплаты: вызывать из payment_processors после успешной покупки/продления
async def on_payment_success(user_id: str) -> None:
    from .payment_hook import on_payment_success as _impl
    await _impl(user_id)

__all__ = ["EVENTS_MODULE_ENABLED", "on_payment_success"]
