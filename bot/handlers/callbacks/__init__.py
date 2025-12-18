"""
Обработчики callback'ов бота
"""
from .instruction_callback import instruction_callback
from .payment_callbacks import (
    select_period_callback, select_server_callback, 
    start_callback_handler
)

__all__ = [
    'instruction_callback', 
    'select_period_callback',
    'select_server_callback',
    'start_callback_handler',
]

