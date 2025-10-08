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
        # Создаем меню покупки напрямую
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        from .menu_states import CallbackData
        
        keyboard = NavigationBuilder.create_keyboard_with_back([
            [InlineKeyboardButton("1 месяц — 100₽", callback_data=CallbackData.SELECT_PERIOD_MONTH)],
            [InlineKeyboardButton("3 месяца — 250₽", callback_data=CallbackData.SELECT_PERIOD_3MONTH)],
        ])
        
        # Используем существующий стиль сообщения
        message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        if message is None:
            logger.error("buy_menu: message is None")
            return
            
        # Импортируем UIMessages из bot.py
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from .bot import UIMessages, safe_edit_or_reply_universal
        
        buy_menu_text = UIMessages.buy_menu_message()
        await safe_edit_or_reply_universal(message, buy_menu_text, reply_markup=keyboard, parse_mode="HTML", menu_type='buy_menu')
    
    async def server_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Выбор сервера"""
        # Импортируем необходимые функции из bot.py
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from .bot import SERVERS_BY_LOCATION, UIEmojis, UIStyles, UIMessages, safe_edit_or_reply_universal, UIButtons
        from .menu_states import CallbackData
        
        message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        if message is None:
            logger.error("server_selection: message is None")
            return
        
        # Получаем менеджер серверов из bot.py
        from .bot import new_client_manager
        health_results = new_client_manager.check_all_servers_health()
        
        # Создаем кнопки для локаций с флагами и статусом
        location_buttons = []
        location_flags = {
            "Finland": "🇫🇮",
            "Latvia": "🇱🇻", 
            "Estonia": "🇪🇪"
        }
        
        # Формируем текст с информацией о локациях
        location_info_text = ""
        
        for location, servers in SERVERS_BY_LOCATION.items():
            if not servers:
                continue
                
            # Проверяем доступность серверов в локации
            available_servers = 0
            total_servers = 0
            
            for server in servers:
                if server["host"] and server["login"] and server["password"]:
                    total_servers += 1
                    if health_results.get(server['name'], False):
                        available_servers += 1
            
            if total_servers == 0:
                continue
                
            flag = location_flags.get(location)
            
            # Определяем статус локации
            if available_servers > 0:
                status_icon = UIEmojis.SUCCESS
                status_text = f"Доступно {available_servers}/{total_servers} серверов"
                button_text = f"{flag} {location} {status_icon}"
                callback_data = f"select_server_{location.lower()}"
            else:
                status_icon = UIEmojis.ERROR
                status_text = "Недоступно"
                button_text = f"{flag} {location} {status_icon}"
                callback_data = f"server_unavailable_{location.lower()}"
            
            location_buttons.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
            
            # Добавляем информацию о локации в текст
            location_info_text += f"{flag} <b>{location}</b> - {status_text}\n"
        
        # Добавляем кнопку "Автовыбор" (только если есть доступные серверы)
        available_servers = sum(1 for is_healthy in health_results.values() if is_healthy)
        if available_servers > 0:
            location_buttons.append([InlineKeyboardButton("🎯 Автовыбор", callback_data=CallbackData.SELECT_SERVER_AUTO)])
            location_info_text += "<b>🎯 Автовыбор</b> - Локация с наименьшей нагрузкой\n"
        
        location_buttons.append([InlineKeyboardButton(f"{UIEmojis.REFRESH} Обновить", callback_data=CallbackData.REFRESH_SERVERS)])
        
        # Определяем текст периода и кнопку назад в зависимости от типа покупки
        pending_period = context.user_data.get("pending_period")
        if pending_period == "month":
            period_text = "1 месяц за 100₽"
            location_buttons.append([UIButtons.back_button()])
        elif pending_period == "3month":
            period_text = "3 месяца за 250₽"
            location_buttons.append([UIButtons.back_button()])
        elif pending_period == "points_month":
            period_text = "1 месяц за 1 балл"
            location_buttons.append([InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data=CallbackData.SPEND_POINTS)])
        else:
            period_text = "Неизвестный период"
            location_buttons.append([UIButtons.back_button()])
        
        keyboard = InlineKeyboardMarkup(location_buttons)
        
        message_text = f"{UIStyles.subheader(f'Выбран период: {period_text}')}\n\n{UIMessages.server_selection_message()}\n\n{location_info_text}"
        
        await safe_edit_or_reply_universal(message, message_text, reply_markup=keyboard, parse_mode="HTML", menu_type='server_selection')
    
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
        # Импортируем необходимые функции из bot.py
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from .bot import ADMIN_IDS, safe_edit_or_reply, UIMessages, safe_edit_or_reply_universal, UIButtons, check_private_chat
        from .menu_states import CallbackData
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        
        if not await check_private_chat(update):
            return
        
        if update.effective_user.id not in ADMIN_IDS:
            await safe_edit_or_reply(update.message, 'Нет доступа.')
            return
        
        # Очищаем состояние всех ConversationHandler'ов при входе в админ меню
        context.user_data.pop('broadcast_text', None)
        context.user_data.pop('broadcast_msg_chat_id', None)
        context.user_data.pop('broadcast_msg_id', None)
        context.user_data.pop('broadcast_details', None)
        context.user_data.pop('config_message_id', None)
        context.user_data.pop('config_chat_id', None)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Логи", callback_data=CallbackData.ADMIN_ERRORS)],
            [InlineKeyboardButton("Проверка серверов", callback_data=CallbackData.ADMIN_CHECK_SERVERS)],
            [InlineKeyboardButton("Уведомления", callback_data=CallbackData.ADMIN_NOTIFICATIONS)],
            [InlineKeyboardButton("Рассылка", callback_data=CallbackData.ADMIN_BROADCAST_START)],
            [InlineKeyboardButton("Изменить дни за балл", callback_data=CallbackData.ADMIN_SET_DAYS_START)],
            [UIButtons.back_button()],
        ])
        message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        if message is None:
            logger.error("admin_menu: message is None")
            return
        
        # Используем единый стиль для админ-меню с фото
        admin_menu_text = UIMessages.admin_menu_message()
        await safe_edit_or_reply_universal(message, admin_menu_text, reply_markup=keyboard, parse_mode="HTML", menu_type='admin_menu')
    
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


class NavigationSystem:
    """Единая система навигации для всего бота"""
    
    def __init__(self, bot_handlers: Dict[str, Any]):
        """
        Инициализация навигационной системы
        
        Args:
            bot_handlers: Словарь с существующими обработчиками из bot.py
        """
        self.bot_handlers = bot_handlers
        self.menu_handlers = MenuHandlers(bot_handlers)
        self.nav_callbacks = NavigationCallbacks(self.menu_handlers)
    
    def navigate_to_state(self, context: ContextTypes.DEFAULT_TYPE, state: str):
        """Переходит к указанному состоянию"""
        nav_manager.push_state(context, state)
    
    def handle_back_navigation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает навигацию назад"""
        return nav_manager.handle_back_navigation(update, context)


class NavigationIntegration:
    """Класс для интеграции навигационной системы с ботом"""
    
    def __init__(self, bot_handlers: Dict[str, Any]):
        """
        Инициализация интеграции
        
        Args:
            bot_handlers: Словарь с существующими обработчиками из bot.py
        """
        self.bot_handlers = bot_handlers
        self.menu_handlers = MenuHandlers(bot_handlers)
        self.nav_callbacks = NavigationCallbacks(self.menu_handlers)
        self.nav_system = NavigationSystem(bot_handlers)
    
    def get_handlers(self) -> list:
        """Возвращает список обработчиков для регистрации в боте"""
        from telegram.ext import CallbackQueryHandler
        
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
