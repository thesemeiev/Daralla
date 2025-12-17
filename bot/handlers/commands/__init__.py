"""
Обработчики команд бота
"""
from .start_handler import start, edit_main_menu
from .instruction_handler import instruction
from .mykey_handler import mykey

__all__ = ['start', 'edit_main_menu', 'instruction', 'mykey']

