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
        nav_manager.register_handler(NavStates.PAYMENT, self.payment)
        nav_manager.register_handler(NavStates.SUBSCRIPTIONS_MENU, self.subscriptions_menu)
        
        # Админ меню
        nav_manager.register_handler(NavStates.ADMIN_MENU, self.admin_menu)
        nav_manager.register_handler(NavStates.ADMIN_ERRORS, self.admin_errors)
        nav_manager.register_handler(NavStates.ADMIN_NOTIFICATIONS, self.admin_notifications)
        nav_manager.register_handler(NavStates.ADMIN_CHECK_SERVERS, self.admin_check_servers)
        nav_manager.register_handler(NavStates.ADMIN_SEARCH_USER, self.admin_search_user)
        nav_manager.register_handler(NavStates.ADMIN_BROADCAST, self.admin_broadcast)
        nav_manager.register_handler(NavStates.ADMIN_CONFIG, self.admin_config)
        nav_manager.register_handler(NavStates.ADMIN_SYNC, self.admin_sync)
        nav_manager.register_handler(NavStates.ADMIN_CHECK_SUBSCRIPTION, self.admin_check_subscription)
        nav_manager.register_handler(NavStates.ADMIN_GIVE_SUBSCRIPTION, self.admin_give_subscription)
    
    async def main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Главное меню"""
        # Импортируем и вызываем edit_main_menu из handlers
        from ..handlers.commands import edit_main_menu
        await edit_main_menu(update, context)
    
    async def instruction_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Меню инструкций"""
        from ..handlers.commands import instruction
        await instruction(update, context)
    
    async def instruction_platform(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Платформы инструкций"""
        # Этот handler не должен вызываться напрямую для callback'ов instr_*
        # Они обрабатываются напрямую через instruction_callback в bot.py
        # Этот handler используется только если navigate_to_state вызывается явно
        # В этом случае мы просто возвращаемся, так как instruction_callback уже обработал все
        logger.debug("instruction_platform called, but instruction_callback should handle instr_* callbacks directly")
        return
    
    async def buy_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Меню покупки"""
        # Создаем меню покупки напрямую
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        from .menu_states import CallbackData, MenuTypes
        from ..utils import UIMessages, safe_edit_or_reply_universal
        
        # Выбираем период (1 или 3 месяца) — 1 подписка = 1 устройство
        keyboard = NavigationBuilder.create_keyboard_with_back([
            [InlineKeyboardButton("1 месяц — 150₽", callback_data=CallbackData.SELECT_PERIOD_MONTH)],
            [InlineKeyboardButton("3 месяца — 350₽", callback_data=CallbackData.SELECT_PERIOD_3MONTH)],
            [InlineKeyboardButton("Промокод", callback_data=CallbackData.PROMO_PURCHASE)],
        ])
        
        # Используем существующий стиль сообщения
        message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        if message is None:
            logger.error("buy_menu: message is None")
            return
        
        buy_menu_text = UIMessages.buy_menu_message()
        await safe_edit_or_reply_universal(message, buy_menu_text, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.BUY_MENU)
    
    async def payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Обработка платежа"""
        from ..handlers.payments import handle_payment
        price = kwargs.get('price')
        period = kwargs.get('period')
        await handle_payment(update, context, price, period)
    
    async def subscriptions_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Меню моих подписок"""
        from ..handlers.commands import mykey
        await mykey(update, context)
    async def admin_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Админ меню"""
        # Импортируем необходимые функции
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        from .menu_states import CallbackData, MenuTypes
        from ..utils import safe_edit_or_reply, UIMessages, safe_edit_or_reply_universal, UIButtons, check_private_chat
        from ..bot import ADMIN_IDS
        
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
            [InlineKeyboardButton("Поиск пользователя", callback_data=CallbackData.ADMIN_SEARCH_USER)],
            [InlineKeyboardButton("Логи", callback_data=CallbackData.ADMIN_ERRORS)],
            [InlineKeyboardButton("Проверка серверов", callback_data=CallbackData.ADMIN_CHECK_SERVERS)],
            [InlineKeyboardButton("Уведомления", callback_data=CallbackData.ADMIN_NOTIFICATIONS)],
            [InlineKeyboardButton("Рассылка", callback_data=CallbackData.ADMIN_BROADCAST_START)],
            [InlineKeyboardButton("Тестовое подтверждение", callback_data=CallbackData.ADMIN_TEST_PAYMENT)],
            [InlineKeyboardButton("Конфигурация", callback_data=CallbackData.ADMIN_CONFIG)],
            [InlineKeyboardButton("Синхронизация", callback_data=CallbackData.ADMIN_SYNC)],
            [InlineKeyboardButton("Проверка подписки", callback_data=CallbackData.ADMIN_CHECK_SUBSCRIPTION)],
            [InlineKeyboardButton("Выдать подписку", callback_data=CallbackData.ADMIN_GIVE_SUBSCRIPTION)],
            [UIButtons.back_button()],
        ])
        message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        if message is None:
            logger.error("admin_menu: message is None")
            return
        
        # Используем единый стиль для админ-меню с фото
        admin_menu_text = UIMessages.admin_menu_message()
        await safe_edit_or_reply_universal(message, admin_menu_text, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_MENU)
    
    async def admin_errors(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Админ логи"""
        from ..handlers.admin import admin_errors
        await admin_errors(update, context)
    
    async def admin_notifications(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Админ уведомления"""
        from ..handlers.admin import admin_notifications
        await admin_notifications(update, context)
    
    async def admin_check_servers(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Админ проверка серверов"""
        from ..handlers.admin import admin_check_servers
        await admin_check_servers(update, context)
    
    async def admin_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Админ рассылка"""
        from ..handlers.admin import admin_broadcast_start
        await admin_broadcast_start(update, context)
    
    async def admin_search_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Поиск пользователя"""
        from ..handlers.admin.admin_user_management import admin_search_user
        await admin_search_user(update, context)
    
    async def admin_user_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Информация о пользователе"""
        from ..handlers.admin.admin_user_management import show_user_info, admin_search_user
        user_id = context.user_data.get('admin_selected_user_id')
        if user_id:
            await show_user_info(update, context, user_id)
        else:
            await admin_search_user(update, context)
    
    async def admin_user_subscriptions(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Подписки пользователя"""
        from ..handlers.admin.admin_user_management import admin_user_subscriptions
        user_id = context.user_data.get('admin_selected_user_id')
        await admin_user_subscriptions(update, context, user_id)
    
    async def admin_user_payments(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Платежи пользователя"""
        from ..handlers.admin.admin_user_management import admin_user_payments
        user_id = context.user_data.get('admin_selected_user_id')
        await admin_user_payments(update, context, user_id)
    
    async def admin_subscription_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Информация о подписке"""
        from ..handlers.admin.admin_subscription_manage import admin_subscription_info
        await admin_subscription_info(update, context)
    
    async def admin_sub_change_limit(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Изменение лимита IP для подписки"""
        from ..handlers.admin.admin_subscription_manage import admin_change_device_limit
        await admin_change_device_limit(update, context)
    
    async def admin_test_payment(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Тестовое подтверждение платежей"""
        from ..handlers.admin.admin_test_payment import admin_test_payment
        # Создаем фиктивный update с message для команды
        if update.callback_query:
            # Если это callback, создаем фиктивный message
            class FakeMessage:
                def __init__(self, original_message):
                    self.from_user = update.effective_user
                    self.chat = original_message.chat
                    self.text = "/admin_test_payment"
                    self.message_id = original_message.message_id
                    self.reply_text = original_message.reply_text
                    self.edit_text = original_message.edit_text
                    self.edit_caption = original_message.edit_caption
                    self.photo = original_message.photo
                    self.caption = original_message.caption
                    self.reply_markup = original_message.reply_markup
            
            fake_update = Update(
                update_id=update.update_id,
                message=FakeMessage(update.callback_query.message)
            )
            await admin_test_payment(fake_update, context)
        else:
            await admin_test_payment(update, context)
    
    async def admin_config(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Конфигурация"""
        from ..handlers.admin.admin_config import admin_config
        await admin_config(update, context)
    
    async def admin_sync(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Синхронизация"""
        from ..handlers.admin.admin_sync import admin_sync
        await admin_sync(update, context)
    
    async def admin_check_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Проверка подписки по токену"""
        from ..handlers.admin.admin_check_subscription import admin_check_subscription
        await admin_check_subscription(update, context)
    
    async def admin_give_subscription(self, update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
        """Выдача подписки пользователю"""
        from ..handlers.admin.admin_give_subscription import admin_give_subscription
        await admin_give_subscription(update, context)
    
    async def admin_give_subscription_period(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка выбора периода подписки"""
        from ..handlers.admin.admin_give_subscription import admin_give_subscription_period
        await admin_give_subscription_period(update, context)
    
    async def admin_give_subscription_continue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Продолжение выдачи подписки для несуществующего пользователя"""
        from ..handlers.admin.admin_give_subscription import admin_give_subscription_continue
        await admin_give_subscription_continue(update, context)
    

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
        # Не отвечаем здесь - handler сам ответит на callback query
        # await query.answer()  # Убрано, чтобы избежать двойного ответа
        
        # Очищаем навигационный стек и идем в главное меню
        nav_manager.clear_stack(context)
        nav_manager.push_state(context, NavStates.MAIN_MENU)
        
        return await nav_manager.navigate_to_state(update, context, NavStates.MAIN_MENU)
    
    async def handle_state_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                  target_state: str, **kwargs):
        """Универсальный обработчик перехода к состоянию"""
        query = update.callback_query
        # Не отвечаем здесь - handler сам ответит на callback query
        # await query.answer()  # Убрано, чтобы избежать двойного ответа
        
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
    
    async def navigate_to_state(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: str, **kwargs):
        """Переходит к указанному состоянию"""
        # Добавляем состояние в стек перед переходом (если его еще нет)
        nav_manager.push_state(context, state)
        return await nav_manager.navigate_to_state(update, context, state, **kwargs)
    
    async def handle_back_navigation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обрабатывает навигацию назад"""
        return await nav_manager.handle_back_navigation(update, context)


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
                lambda u, c: self.nav_callbacks.handle_state_callback(u, c, NavStates.SUBSCRIPTIONS_MENU),
                pattern=f"^{CallbackData.MY_SUBSCRIPTIONS}$"
            ),
            CallbackQueryHandler(
                lambda u, c: self.nav_callbacks.handle_state_callback(u, c, NavStates.SUBSCRIPTIONS_MENU),
                pattern=f"^{CallbackData.SUBSCRIPTIONS_MENU}$"
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
                lambda u, c: self.nav_callbacks.handle_state_callback(u, c, NavStates.ADMIN_SEARCH_USER),
                pattern=f"^{CallbackData.ADMIN_SEARCH_USER}$"
            ),
            CallbackQueryHandler(
                lambda u, c: self.nav_callbacks.handle_state_callback(u, c, NavStates.ADMIN_BROADCAST),
                pattern=f"^{CallbackData.ADMIN_BROADCAST_START}$"
            ),
            # Тестовое подтверждение - вызываем команду напрямую
            CallbackQueryHandler(
                lambda u, c: self.menu_handlers.admin_test_payment(u, c),
                pattern=f"^{CallbackData.ADMIN_TEST_PAYMENT}$"
            ),
            CallbackQueryHandler(
                lambda u, c: self.nav_callbacks.handle_state_callback(u, c, NavStates.ADMIN_CONFIG),
                pattern=f"^{CallbackData.ADMIN_CONFIG}$"
            ),
            CallbackQueryHandler(
                lambda u, c: self.nav_callbacks.handle_state_callback(u, c, NavStates.ADMIN_SYNC),
                pattern=f"^{CallbackData.ADMIN_SYNC}$"
            ),
            CallbackQueryHandler(
                lambda u, c: self.nav_callbacks.handle_state_callback(u, c, NavStates.ADMIN_CHECK_SUBSCRIPTION),
                pattern=f"^{CallbackData.ADMIN_CHECK_SUBSCRIPTION}$"
            ),
            CallbackQueryHandler(
                lambda u, c: self.nav_callbacks.handle_state_callback(u, c, NavStates.ADMIN_GIVE_SUBSCRIPTION),
                pattern=f"^{CallbackData.ADMIN_GIVE_SUBSCRIPTION}$"
            ),
            # Callback для выбора периода подписки
            CallbackQueryHandler(
                lambda u, c: self.menu_handlers.admin_give_subscription_period(u, c),
                pattern=r"^admin_give_sub_period:"
            ),
            # Callback для продолжения выдачи подписки несуществующему пользователю
            CallbackQueryHandler(
                lambda u, c: self.menu_handlers.admin_give_subscription_continue(u, c),
                pattern=r"^admin_give_sub_continue:"
            ),
            # Обновление админских меню (остаются в том же состоянии)
            CallbackQueryHandler(
                lambda u, c: self.menu_handlers.admin_errors(u, c),
                pattern=f"^{CallbackData.ADMIN_ERRORS_REFRESH}$"
            ),
            CallbackQueryHandler(
                lambda u, c: self.menu_handlers.admin_notifications(u, c),
                pattern=f"^{CallbackData.ADMIN_NOTIFICATIONS_REFRESH}$"
            ),
        ]

