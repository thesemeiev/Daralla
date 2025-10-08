"""
Обработчики всех меню бота
"""

import logging
from typing import Optional, List, Dict, Any
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from .navigation import nav_manager, NavigationBuilder
from .menu_states import NavStates, CallbackData, MenuTypes

logger = logging.getLogger(__name__)

class MenuHandlers:
    """Класс с обработчиками всех меню"""
    
    def __init__(self, bot_handlers: Dict[str, Any]):
        """
        Инициализация с передачей существующих обработчиков из bot.py
        
        Args:
            bot_handlers: Словарь с функциями-обработчиками из основного бота
        """
        self.handlers = bot_handlers
        self._register_handlers()
    
    def _register_handlers(self):
        """Регистрирует все обработчики в навигационном менеджере"""
        # Основные меню
        nav_manager.register_handler(NavStates.MAIN_MENU, self.main_menu)
        nav_manager.register_handler(NavStates.INSTRUCTION_MENU, self.instruction_menu)
        nav_manager.register_handler(NavStates.INSTRUCTION_PLATFORM, self.instruction_platform)
        nav_manager.register_handler(NavStates.BUY_MENU, self.buy_menu)
        nav_manager.register_handler(NavStates.SERVER_SELECTION, self.server_selection)
        nav_manager.register_handler(NavStates.PAYMENT, self.payment)
        nav_manager.register_handler(NavStates.MYKEYS_MENU, self.mykeys_menu)
        nav_manager.register_handler(NavStates.POINTS_MENU, self.points_menu)
        nav_manager.register_handler(NavStates.REFERRAL_MENU, self.referral_menu)
        nav_manager.register_handler(NavStates.EXTEND_KEY, self.extend_key)
        nav_manager.register_handler(NavStates.RENAME_KEY, self.rename_key)
        
        # Админ меню
        nav_manager.register_handler(NavStates.ADMIN_MENU, self.admin_menu)
        nav_manager.register_handler(NavStates.ADMIN_ERRORS, self.admin_errors)
        nav_manager.register_handler(NavStates.ADMIN_NOTIFICATIONS, self.admin_notifications)
        nav_manager.register_handler(NavStates.ADMIN_CHECK_SERVERS, self.admin_check_servers)
        nav_manager.register_handler(NavStates.ADMIN_BROADCAST, self.admin_broadcast)
        nav_manager.register_handler(NavStates.ADMIN_SET_DAYS, self.admin_set_days)
    
    async def main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Главное меню"""
        # Используем существующий обработчик из bot.py
        if 'edit_main_menu' in self.handlers:
            await self.handlers['edit_main_menu'](update, context)
        else:
            logger.error("edit_main_menu handler not found")
    
    async def instruction_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Меню инструкций"""
        if 'instruction' in self.handlers:
            await self.handlers['instruction'](update, context)
        else:
            logger.error("instruction handler not found")
    
    async def instruction_platform(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Платформы инструкций"""
        if 'instruction_callback' in self.handlers:
            await self.handlers['instruction_callback'](update, context)
        else:
            logger.error("instruction_callback handler not found")
    
    async def buy_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Меню покупки"""
        if 'buy_menu_handler' in self.handlers:
            await self.handlers['buy_menu_handler'](update, context)
        else:
            logger.error("buy_menu_handler not found")
    
    async def server_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Выбор сервера"""
        if 'server_selection_menu' in self.handlers:
            await self.handlers['server_selection_menu'](update, context)
        else:
            logger.error("server_selection_menu handler not found")
    
    async def payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Обработка платежа"""
        if 'handle_payment' in self.handlers:
            price = kwargs.get('price')
            period = kwargs.get('period')
            await self.handlers['handle_payment'](update, context, price, period)
        else:
            logger.error("handle_payment handler not found")
    
    async def mykeys_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Меню моих ключей"""
        if 'mykey' in self.handlers:
            await self.handlers['mykey'](update, context)
        else:
            logger.error("mykey handler not found")
    
    async def points_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Меню баллов"""
        if 'points_callback' in self.handlers:
            await self.handlers['points_callback'](update, context)
        else:
            logger.error("points_callback handler not found")
    
    async def referral_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Меню рефералов"""
        if 'referral_callback' in self.handlers:
            await self.handlers['referral_callback'](update, context)
        else:
            logger.error("referral_callback handler not found")
    
    async def extend_key(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Продление ключа"""
        if 'extend_key_callback' in self.handlers:
            await self.handlers['extend_key_callback'](update, context)
        else:
            logger.error("extend_key_callback handler not found")
    
    async def rename_key(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Переименование ключа"""
        if 'rename_key_callback' in self.handlers:
            await self.handlers['rename_key_callback'](update, context)
        else:
            logger.error("rename_key_callback handler not found")
    
    async def admin_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Админ меню"""
        if 'admin_menu' in self.handlers:
            await self.handlers['admin_menu'](update, context)
        else:
            logger.error("admin_menu handler not found")
    
    async def admin_errors(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Админ логи"""
        if 'admin_errors' in self.handlers:
            await self.handlers['admin_errors'](update, context)
        else:
            logger.error("admin_errors handler not found")
    
    async def admin_notifications(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Админ уведомления"""
        if 'admin_notifications' in self.handlers:
            await self.handlers['admin_notifications'](update, context)
        else:
            logger.error("admin_notifications handler not found")
    
    async def admin_check_servers(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Админ проверка серверов"""
        if 'admin_check_servers' in self.handlers:
            await self.handlers['admin_check_servers'](update, context)
        else:
            logger.error("admin_check_servers handler not found")
    
    async def admin_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Админ рассылка"""
        if 'admin_broadcast_start' in self.handlers:
            await self.handlers['admin_broadcast_start'](update, context)
        else:
            logger.error("admin_broadcast_start handler not found")
    
    async def admin_set_days(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Админ настройка дней"""
        if 'admin_set_days_start' in self.handlers:
            await self.handlers['admin_set_days_start'](update, context)
        else:
            logger.error("admin_set_days_start handler not found")

class NavigationCallbacks:
    """Обработчики навигационных callback'ов"""
    
    def __init__(self, menu_handlers: MenuHandlers):
        self.menu_handlers = menu_handlers
    
    async def handle_back_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик кнопки 'Назад'"""
        return await nav_manager.handle_back_navigation(update, context)
    
    async def handle_main_menu_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик кнопки 'Главное меню'"""
        query = update.callback_query
        await query.answer()
        
        # Очищаем навигационный стек и идем в главное меню
        nav_manager.clear_stack(context)
        nav_manager.push_state(context, NavStates.MAIN_MENU)
        
        return await nav_manager.navigate_to_state(update, context, NavStates.MAIN_MENU)
    
    async def handle_state_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                  target_state: str, **kwargs):
        """Универсальный обработчик перехода к состоянию"""
        query = update.callback_query
        await query.answer()
        
        # Добавляем состояние в стек
        nav_manager.push_state(context, target_state)
        
        # Переходим к состоянию
        return await nav_manager.navigate_to_state(update, context, target_state, **kwargs)
