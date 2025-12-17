"""
Обработчики callback'ов бота
"""
from .instruction_callback import instruction_callback
from .extend_key_callback import extend_key_callback
from .payment_callbacks import (
    select_period_callback, select_server_callback, 
    start_callback_handler, extend_period_callback
)

__all__ = [
    'instruction_callback', 
    'extend_key_callback', 
    'select_period_callback',
    'select_server_callback',
    'start_callback_handler',
    'extend_period_callback',
]

