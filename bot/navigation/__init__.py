"""
Модуль навигации бота
"""
from .navigation import nav_manager, NavigationBuilder, NavigationManager
from .menu_states import NavStates, CallbackData, MenuTypes, STATE_TO_HANDLER, CALLBACK_TO_STATE
from .menu_handlers import MenuHandlers, NavigationSystem, NavigationIntegration

__all__ = [
    'nav_manager', 'NavigationBuilder', 'NavigationManager',
    'NavStates', 'CallbackData', 'MenuTypes', 'STATE_TO_HANDLER', 'CALLBACK_TO_STATE',
    'MenuHandlers', 'NavigationSystem', 'NavigationIntegration'
]

