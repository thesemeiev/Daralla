"""
Централизованная система навигации для Telegram бота
"""

import logging
from typing import Optional, List, Dict, Any
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from .menu_states import NavStates, CallbackData, STATE_TO_HANDLER

logger = logging.getLogger(__name__)

class NavigationManager:
    """Менеджер навигационного стека"""
    
    def __init__(self, max_stack_size: int = 10):
        self.max_stack_size = max_stack_size
        self.handlers = {}
    
    def register_handler(self, state: str, handler_func):
        """Регистрирует обработчик для состояния"""
        self.handlers[state] = handler_func
    
    def push_state(self, context: ContextTypes.DEFAULT_TYPE, state: str) -> None:
        """Добавляет состояние в навигационный стек"""
        stack = context.user_data.setdefault('nav_stack', [])
        
        # Если стек пустой и добавляем не главное меню, сначала добавляем главное меню
        if not stack and state != NavStates.MAIN_MENU:
            stack.append(NavStates.MAIN_MENU)
            logger.info(f"PUSH: {NavStates.MAIN_MENU} (auto) -> Stack: {stack}")
        
        # Если последнее состояние отличается от нового, добавляем
        # Это позволяет сохранить историю навигации
        if not stack or stack[-1] != state:
            # Ограничиваем размер стека
            if len(stack) >= self.max_stack_size:
                stack.pop(0)  # Удаляем самый старый элемент
            
            # Добавляем состояние в конец
            stack.append(state)
            logger.info(f"PUSH: {state} -> Stack: {stack}")
        else:
            # Если пытаемся добавить то же состояние, что и текущее, не добавляем
            logger.debug(f"PUSH: {state} already on top, skipping")
    
    def pop_state(self, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        """Удаляет последнее состояние из стека и возвращает предыдущее"""
        stack = context.user_data.get('nav_stack', [])
        if stack:
            popped = stack.pop()
            prev_state = stack[-1] if stack else None
            logger.info(f"POP: {popped} -> Stack: {stack} -> Prev: {prev_state}")
            return prev_state
        logger.info("POP: empty stack")
        return None
    
    def get_current_state(self, context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        """Возвращает текущее состояние"""
        stack = context.user_data.get('nav_stack', [])
        return stack[-1] if stack else None
    
    def clear_stack(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Очищает навигационный стек"""
        context.user_data['nav_stack'] = []
        logger.info("CLEAR: Navigation stack cleared")
    
    def get_stack(self, context: ContextTypes.DEFAULT_TYPE) -> List[str]:
        """Возвращает копию навигационного стека"""
        return context.user_data.get('nav_stack', []).copy()
    
    def is_empty(self, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Проверяет, пуст ли навигационный стек"""
        return len(context.user_data.get('nav_stack', [])) == 0
    
    def validate_stack(self, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Проверяет корректность навигационного стека"""
        valid_states = set(NavStates.__dict__.values())
        stack = context.user_data.get('nav_stack', [])
        return all(state in valid_states for state in stack)
    
    async def navigate_to_state(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                              target_state: str, **kwargs) -> bool:
        """Переходит к указанному состоянию"""
        try:
            # Убеждаемся, что состояние добавлено в стек перед вызовом обработчика
            self.push_state(context, target_state)
            
            if target_state in self.handlers:
                # Устанавливаем флаг, чтобы функции знали, что они вызываются через навигационную систему
                context.user_data['_nav_called'] = True
                try:
                    await self.handlers[target_state](update, context, **kwargs)
                finally:
                    # Удаляем флаг после вызова
                    context.user_data.pop('_nav_called', None)
                return True
            else:
                logger.error(f"Handler not found for state: {target_state}")
                return False
        except Exception as e:
            logger.error(f"Error navigating to {target_state}: {e}")
            context.user_data.pop('_nav_called', None)
            return False
    
    async def handle_back_navigation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Обрабатывает навигацию назад"""
        query = update.callback_query
        from ..utils import safe_answer_callback_query
        await safe_answer_callback_query(query)
        
        logger.info(f"← BACK_NAVIGATION: User {query.from_user.id}")
        logger.info(f"← BACK_NAVIGATION: Current stack: {self.get_stack(context)}")
        
        stack = self.get_stack(context)
        
        # Если стек пустой или содержит только одно состояние - идем в главное меню
        if len(stack) <= 1:
            logger.info("← BACK_NAVIGATION: Stack has 0-1 states, going to main menu")
            self.clear_stack(context)
            self.push_state(context, NavStates.MAIN_MENU)
            return await self.navigate_to_state(update, context, NavStates.MAIN_MENU)
        
        # Удаляем текущее состояние из стека
        current_state = stack[-1]
        stack.pop()
        
        # Получаем предыдущее состояние
        prev_state = stack[-1] if stack else None
        
        logger.info(f"← BACK_NAVIGATION: Current={current_state}, Prev={prev_state}, Stack after pop: {stack}")
        
        # Обновляем стек в контексте
        context.user_data['nav_stack'] = stack
        
        if prev_state is None:
            # Стек пустой после удаления - идем в главное меню
            logger.info("← BACK_NAVIGATION: No previous state, going to main menu")
            self.push_state(context, NavStates.MAIN_MENU)
            return await self.navigate_to_state(update, context, NavStates.MAIN_MENU)
        
        
        # Обычная навигация - возвращаемся к предыдущему состоянию
        # НЕ добавляем prev_state в стек через push_state, так как он уже там
        # Но navigate_to_state может попытаться добавить его снова, поэтому проверяем
        logger.info(f"← BACK_NAVIGATION: Navigating to {prev_state}")
        # Вызываем обработчик напрямую, чтобы не добавлять состояние в стек повторно
        # Устанавливаем флаг _nav_called, чтобы функции не вызывали navigate_to_state повторно
        if prev_state in self.handlers:
            context.user_data['_nav_called'] = True
            try:
                await self.handlers[prev_state](update, context)
            finally:
                context.user_data.pop('_nav_called', None)
            return True
        else:
            logger.error(f"Handler not found for state: {prev_state}")
            return False

class NavigationBuilder:
    """Строитель навигационных элементов"""
    
    @staticmethod
    def create_back_button(text: str = "Назад", callback_data: str = CallbackData.BACK) -> InlineKeyboardButton:
        """Создает кнопку 'Назад'"""
        return InlineKeyboardButton(f"← {text}", callback_data=callback_data)
    
    @staticmethod
    def create_main_menu_button(text: str = "Главное меню", callback_data: str = CallbackData.MAIN_MENU) -> InlineKeyboardButton:
        """Создает кнопку 'Главное меню'"""
        return InlineKeyboardButton(f" {text}", callback_data=callback_data)
    
    @staticmethod
    def create_keyboard_with_back(buttons: List[List[InlineKeyboardButton]], 
                                back_text: str = "Назад") -> InlineKeyboardMarkup:
        """Создает клавиатуру с кнопкой 'Назад'"""
        keyboard_buttons = buttons.copy()
        keyboard_buttons.append([NavigationBuilder.create_back_button(back_text)])
        return InlineKeyboardMarkup(keyboard_buttons)
    
    @staticmethod
    def create_keyboard_with_main_menu(buttons: List[List[InlineKeyboardButton]], 
                                     main_text: str = "Главное меню") -> InlineKeyboardMarkup:
        """Создает клавиатуру с кнопкой 'Главное меню'"""
        keyboard_buttons = buttons.copy()
        keyboard_buttons.append([NavigationBuilder.create_main_menu_button(main_text)])
        return InlineKeyboardMarkup(keyboard_buttons)

class NavigationValidator:
    """Валидатор навигации"""
    
    @staticmethod
    def validate_state_transition(from_state: str, to_state: str) -> bool:
        """Проверяет, разрешен ли переход между состояниями"""
        # Запрещенные переходы
        forbidden_transitions = {
            (NavStates.ADMIN_ERRORS, NavStates.ADMIN_ERRORS),  # Нельзя остаться в том же админ-меню
            (NavStates.ADMIN_NOTIFICATIONS, NavStates.ADMIN_NOTIFICATIONS),
            (NavStates.ADMIN_CHECK_SERVERS, NavStates.ADMIN_CHECK_SERVERS),
        }
        
        return (from_state, to_state) not in forbidden_transitions
    
    @staticmethod
    def get_allowed_transitions(from_state: str) -> List[str]:
        """Возвращает список разрешенных переходов из состояния"""
        allowed = {
            NavStates.MAIN_MENU: [NavStates.INSTRUCTION_MENU, NavStates.BUY_MENU, NavStates.SUBSCRIPTIONS_MENU, NavStates.ADMIN_MENU],
            NavStates.INSTRUCTION_MENU: [NavStates.INSTRUCTION_PLATFORM, NavStates.MAIN_MENU],
            NavStates.INSTRUCTION_PLATFORM: [NavStates.INSTRUCTION_MENU],
            NavStates.BUY_MENU: [NavStates.PAYMENT, NavStates.MAIN_MENU],
            NavStates.PAYMENT: [NavStates.SUBSCRIPTIONS_MENU, NavStates.MAIN_MENU],
            NavStates.SUBSCRIPTIONS_MENU: [NavStates.MAIN_MENU],
            NavStates.ADMIN_MENU: [NavStates.ADMIN_ERRORS, NavStates.ADMIN_NOTIFICATIONS, NavStates.ADMIN_CHECK_SERVERS, NavStates.ADMIN_BROADCAST, NavStates.MAIN_MENU],
            NavStates.ADMIN_ERRORS: [NavStates.ADMIN_MENU],
            NavStates.ADMIN_NOTIFICATIONS: [NavStates.ADMIN_MENU],
            NavStates.ADMIN_CHECK_SERVERS: [NavStates.ADMIN_MENU],
            NavStates.ADMIN_BROADCAST: [NavStates.ADMIN_MENU],
        }
        
        return allowed.get(from_state, [])

# Глобальный экземпляр менеджера навигации
nav_manager = NavigationManager()

