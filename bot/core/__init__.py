"""
Core модули бота
"""
from .startup import on_startup, notify_admin
from .tasks import start_background_tasks

__all__ = [
    'on_startup',
    'notify_admin',
    'start_background_tasks',
]
