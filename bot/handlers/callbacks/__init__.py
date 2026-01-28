"""
Обработчики callback'ов бота
"""
from .instruction_callback import instruction_callback
from .payment_callbacks import (
    select_period_callback, 
    start_callback_handler
)
from .link_telegram_callback import link_telegram_confirm_callback

__all__ = [
    'instruction_callback', 
    'select_period_callback',
    'start_callback_handler',
    'link_telegram_confirm_callback',
]

