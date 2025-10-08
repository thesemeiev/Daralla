"""
Интеграция новой системы навигации с существующим ботом
"""

import logging
from typing import Dict, Any
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler

from .navigation import nav_manager, NavigationBuilder
from .menu_handlers import MenuHandlers, NavigationCallbacks
from .menu_states import NavStates, CallbackData

logger = logging.getLogger(__name__)

class NavigationIntegration:
    """Класс для интеграции новой системы навигации"""
    
    def __init__(self, bot_handlers: Dict[str, Any]):
        """
        Инициализация интеграции
        
        Args:
            bot_handlers: Словарь с существующими обработчиками из bot.py
        """
        self.bot_handlers = bot_handlers
        self.menu_handlers = MenuHandlers(bot_handlers)
        self.nav_callbacks = NavigationCallbacks(self.menu_handlers)
        
        # Регистрируем обработчики
        self._register_handlers()
    
    def _register_handlers(self):
        """Регистрирует все обработчики в навигационном менеджере"""
        # Основные меню
        nav_manager.register_handler(NavStates.MAIN_MENU, self.menu_handlers.main_menu)
        nav_manager.register_handler(NavStates.INSTRUCTION_MENU, self.menu_handlers.instruction_menu)
        nav_manager.register_handler(NavStates.INSTRUCTION_PLATFORM, self.menu_handlers.instruction_platform)
        nav_manager.register_handler(NavStates.BUY_MENU, self.menu_handlers.buy_menu)
        nav_manager.register_handler(NavStates.SERVER_SELECTION, self.menu_handlers.server_selection)
        nav_manager.register_handler(NavStates.PAYMENT, self.menu_handlers.payment)
        nav_manager.register_handler(NavStates.MYKEYS_MENU, self.menu_handlers.mykeys_menu)
        nav_manager.register_handler(NavStates.POINTS_MENU, self.menu_handlers.points_menu)
        nav_manager.register_handler(NavStates.REFERRAL_MENU, self.menu_handlers.referral_menu)
        nav_manager.register_handler(NavStates.EXTEND_KEY, self.menu_handlers.extend_key)
        nav_manager.register_handler(NavStates.RENAME_KEY, self.menu_handlers.rename_key)
        
        # Админ меню
        nav_manager.register_handler(NavStates.ADMIN_MENU, self.menu_handlers.admin_menu)
        nav_manager.register_handler(NavStates.ADMIN_ERRORS, self.menu_handlers.admin_errors)
        nav_manager.register_handler(NavStates.ADMIN_NOTIFICATIONS, self.menu_handlers.admin_notifications)
        nav_manager.register_handler(NavStates.ADMIN_CHECK_SERVERS, self.menu_handlers.admin_check_servers)
        nav_manager.register_handler(NavStates.ADMIN_BROADCAST, self.menu_handlers.admin_broadcast)
        nav_manager.register_handler(NavStates.ADMIN_SET_DAYS, self.menu_handlers.admin_set_days)
    
    def get_handlers(self) -> list:
        """Возвращает список обработчиков для регистрации в боте"""
        return [
            # Универсальная кнопка "Назад"
            CallbackQueryHandler(
                self.nav_callbacks.handle_back_callback, 
                pattern=f"^{CallbackData.BACK}$"
            ),
            
            # Кнопка "Главное меню"
            CallbackQueryHandler(
                self.nav_callbacks.handle_main_menu_callback, 
                pattern=f"^{CallbackData.MAIN_MENU}$"
            ),
            
            # Переходы к основным меню
            CallbackQueryHandler(
                lambda u, c: self.nav_callbacks.handle_state_callback(u, c, NavStates.INSTRUCTION_MENU),
                pattern=f"^{CallbackData.INSTRUCTION}$"
            ),
            CallbackQueryHandler(
                lambda u, c: self.nav_callbacks.handle_state_callback(u, c, NavStates.BUY_MENU),
                pattern=f"^{CallbackData.BUY_VPN}$"
            ),
            CallbackQueryHandler(
                lambda u, c: self.nav_callbacks.handle_state_callback(u, c, NavStates.MYKEYS_MENU),
                pattern=f"^{CallbackData.MY_KEYS}$"
            ),
            CallbackQueryHandler(
                lambda u, c: self.nav_callbacks.handle_state_callback(u, c, NavStates.POINTS_MENU),
                pattern=f"^{CallbackData.POINTS}$"
            ),
            CallbackQueryHandler(
                lambda u, c: self.nav_callbacks.handle_state_callback(u, c, NavStates.REFERRAL_MENU),
                pattern=f"^{CallbackData.REFERRAL}$"
            ),
            
            # Админ меню
            CallbackQueryHandler(
                lambda u, c: self.nav_callbacks.handle_state_callback(u, c, NavStates.ADMIN_MENU),
                pattern=f"^{CallbackData.ADMIN_MENU}$"
            ),
            CallbackQueryHandler(
                lambda u, c: self.nav_callbacks.handle_state_callback(u, c, NavStates.ADMIN_ERRORS),
                pattern=f"^{CallbackData.ADMIN_ERRORS}$"
            ),
            CallbackQueryHandler(
                lambda u, c: self.nav_callbacks.handle_state_callback(u, c, NavStates.ADMIN_NOTIFICATIONS),
                pattern=f"^{CallbackData.ADMIN_NOTIFICATIONS}$"
            ),
            CallbackQueryHandler(
                lambda u, c: self.nav_callbacks.handle_state_callback(u, c, NavStates.ADMIN_CHECK_SERVERS),
                pattern=f"^{CallbackData.ADMIN_CHECK_SERVERS}$"
            ),
            CallbackQueryHandler(
                lambda u, c: self.nav_callbacks.handle_state_callback(u, c, NavStates.ADMIN_BROADCAST),
                pattern=f"^{CallbackData.ADMIN_BROADCAST_START}$"
            ),
            CallbackQueryHandler(
                lambda u, c: self.nav_callbacks.handle_state_callback(u, c, NavStates.ADMIN_SET_DAYS),
                pattern=f"^{CallbackData.ADMIN_SET_DAYS_START}$"
            ),
        ]
    
    def create_navigation_buttons(self, menu_type: str) -> InlineKeyboardMarkup:
        """Создает навигационные кнопки для меню"""
        if menu_type == 'main_menu':
            # Главное меню - только основные кнопки
            return None
        
        # Для всех остальных меню добавляем кнопку "Назад"
        return NavigationBuilder.create_keyboard_with_back([])
    
    def update_existing_handlers(self):
        """Обновляет существующие обработчики для работы с новой навигацией"""
        # Здесь можно добавить логику для модификации существующих обработчиков
        # чтобы они использовали новую систему навигации
        pass

# Пример использования в bot.py:
"""
# В начале bot.py добавить:
from .navigation_integration import NavigationIntegration

# После создания всех обработчиков:
bot_handlers = {
    'edit_main_menu': edit_main_menu,
    'instruction': instruction,
    'instruction_callback': instruction_callback,
    'buy_menu_handler': buy_menu_handler,
    'server_selection_menu': server_selection_menu,
    'handle_payment': handle_payment,
    'mykey': mykey,
    'points_callback': points_callback,
    'referral_callback': referral_callback,
    'extend_key_callback': extend_key_callback,
    'rename_key_callback': rename_key_callback,
    'admin_menu': admin_menu,
    'admin_errors': admin_errors,
    'admin_notifications': admin_notifications,
    'admin_check_servers': admin_check_servers,
    'admin_broadcast_start': admin_broadcast_start,
    'admin_set_days_start': admin_set_days_start,
}

# Создаем интеграцию
nav_integration = NavigationIntegration(bot_handlers)

# В main() функции добавляем новые обработчики:
app.add_handlers(nav_integration.get_handlers())
"""
