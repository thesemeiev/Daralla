"""
Тесты для новой системы навигации
"""

import pytest
from unittest.mock import Mock, AsyncMock
from telegram import Update, CallbackQuery, User, Message, Chat
from telegram.ext import ContextTypes

from .navigation import NavigationManager, NavigationBuilder, NavigationValidator
from .menu_states import NavStates, CallbackData

class TestNavigationManager:
    """Тесты для NavigationManager"""
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        self.nav_manager = NavigationManager(max_stack_size=5)
        self.context = Mock()
        self.context.user_data = {}
    
    def test_push_state(self):
        """Тест добавления состояния в стек"""
        self.nav_manager.push_state(self.context, NavStates.MAIN_MENU)
        assert self.context.user_data['nav_stack'] == [NavStates.MAIN_MENU]
        
        self.nav_manager.push_state(self.context, NavStates.BUY_MENU)
        assert self.context.user_data['nav_stack'] == [NavStates.MAIN_MENU, NavStates.BUY_MENU]
    
    def test_push_duplicate_state(self):
        """Тест добавления дублирующего состояния"""
        self.nav_manager.push_state(self.context, NavStates.MAIN_MENU)
        self.nav_manager.push_state(self.context, NavStates.MAIN_MENU)
        
        # Дубликат не должен добавляться
        assert self.context.user_data['nav_stack'] == [NavStates.MAIN_MENU]
    
    def test_pop_state(self):
        """Тест удаления состояния из стека"""
        self.nav_manager.push_state(self.context, NavStates.MAIN_MENU)
        self.nav_manager.push_state(self.context, NavStates.BUY_MENU)
        
        prev_state = self.nav_manager.pop_state(self.context)
        assert prev_state == NavStates.MAIN_MENU
        assert self.context.user_data['nav_stack'] == [NavStates.MAIN_MENU]
    
    def test_pop_empty_stack(self):
        """Тест удаления из пустого стека"""
        prev_state = self.nav_manager.pop_state(self.context)
        assert prev_state is None
    
    def test_max_stack_size(self):
        """Тест ограничения размера стека"""
        # Добавляем больше состояний, чем max_stack_size
        for i in range(7):
            self.nav_manager.push_state(self.context, f"state_{i}")
        
        stack = self.context.user_data['nav_stack']
        assert len(stack) == 5  # max_stack_size
        assert stack[0] == "state_2"  # Первые два удалены
        assert stack[-1] == "state_6"  # Последнее добавленное
    
    def test_clear_stack(self):
        """Тест очистки стека"""
        self.nav_manager.push_state(self.context, NavStates.MAIN_MENU)
        self.nav_manager.push_state(self.context, NavStates.BUY_MENU)
        
        self.nav_manager.clear_stack(self.context)
        assert self.context.user_data['nav_stack'] == []
    
    def test_get_current_state(self):
        """Тест получения текущего состояния"""
        assert self.nav_manager.get_current_state(self.context) is None
        
        self.nav_manager.push_state(self.context, NavStates.MAIN_MENU)
        assert self.nav_manager.get_current_state(self.context) == NavStates.MAIN_MENU
    
    def test_is_empty(self):
        """Тест проверки пустого стека"""
        assert self.nav_manager.is_empty(self.context) is True
        
        self.nav_manager.push_state(self.context, NavStates.MAIN_MENU)
        assert self.nav_manager.is_empty(self.context) is False
    
    def test_validate_stack(self):
        """Тест валидации стека"""
        # Валидный стек
        self.nav_manager.push_state(self.context, NavStates.MAIN_MENU)
        self.nav_manager.push_state(self.context, NavStates.BUY_MENU)
        assert self.nav_manager.validate_stack(self.context) is True
        
        # Невалидный стек
        self.context.user_data['nav_stack'] = ['invalid_state']
        assert self.nav_manager.validate_stack(self.context) is False

class TestNavigationBuilder:
    """Тесты для NavigationBuilder"""
    
    def test_create_back_button(self):
        """Тест создания кнопки 'Назад'"""
        button = NavigationBuilder.create_back_button("Назад")
        assert button.text == "🔙 Назад"
        assert button.callback_data == CallbackData.BACK
    
    def test_create_main_menu_button(self):
        """Тест создания кнопки 'Главное меню'"""
        button = NavigationBuilder.create_main_menu_button("Главное меню")
        assert button.text == "🏠 Главное меню"
        assert button.callback_data == CallbackData.MAIN_MENU
    
    def test_create_keyboard_with_back(self):
        """Тест создания клавиатуры с кнопкой 'Назад'"""
        from telegram import InlineKeyboardButton
        
        buttons = [
            [InlineKeyboardButton("Кнопка 1", callback_data="btn1")]
        ]
        keyboard = NavigationBuilder.create_keyboard_with_back(buttons)
        
        assert len(keyboard.inline_keyboard) == 2
        assert keyboard.inline_keyboard[0][0].text == "Кнопка 1"
        assert keyboard.inline_keyboard[1][0].text == "🔙 Назад"
    
    def test_create_keyboard_with_main_menu(self):
        """Тест создания клавиатуры с кнопкой 'Главное меню'"""
        from telegram import InlineKeyboardButton
        
        buttons = [
            [InlineKeyboardButton("Кнопка 1", callback_data="btn1")]
        ]
        keyboard = NavigationBuilder.create_keyboard_with_main_menu(buttons)
        
        assert len(keyboard.inline_keyboard) == 2
        assert keyboard.inline_keyboard[0][0].text == "Кнопка 1"
        assert keyboard.inline_keyboard[1][0].text == "🏠 Главное меню"

class TestNavigationValidator:
    """Тесты для NavigationValidator"""
    
    def test_validate_state_transition(self):
        """Тест валидации переходов между состояниями"""
        # Разрешенный переход
        assert NavigationValidator.validate_state_transition(
            NavStates.MAIN_MENU, 
            NavStates.BUY_MENU
        ) is True
        
        # Запрещенный переход
        assert NavigationValidator.validate_state_transition(
            NavStates.PAYMENT, 
            NavStates.SERVER_SELECTION
        ) is False
    
    def test_get_allowed_transitions(self):
        """Тест получения разрешенных переходов"""
        allowed = NavigationValidator.get_allowed_transitions(NavStates.MAIN_MENU)
        expected = [
            NavStates.INSTRUCTION_MENU, 
            NavStates.BUY_MENU, 
            NavStates.MYKEYS_MENU, 
            NavStates.POINTS_MENU, 
            NavStates.REFERRAL_MENU, 
            NavStates.ADMIN_MENU
        ]
        assert set(allowed) == set(expected)

@pytest.mark.asyncio
class TestNavigationIntegration:
    """Тесты интеграции навигации"""
    
    def setup_method(self):
        """Настройка перед каждым тестом"""
        self.nav_manager = NavigationManager()
        self.context = Mock()
        self.context.user_data = {}
        
        # Мокаем обработчики
        self.mock_handlers = {
            'edit_main_menu': AsyncMock(),
            'instruction': AsyncMock(),
            'mykey': AsyncMock(),
        }
        
        # Регистрируем обработчики
        for state, handler in self.mock_handlers.items():
            self.nav_manager.register_handler(state, handler)
    
    async def test_navigate_to_state(self):
        """Тест навигации к состоянию"""
        result = await self.nav_manager.navigate_to_state(
            Mock(), self.context, NavStates.MAIN_MENU
        )
        
        assert result is True
        self.mock_handlers['edit_main_menu'].assert_called_once()
    
    async def test_navigate_to_unknown_state(self):
        """Тест навигации к неизвестному состоянию"""
        result = await self.nav_manager.navigate_to_state(
            Mock(), self.context, 'unknown_state'
        )
        
        assert result is False
    
    async def test_handle_back_navigation(self):
        """Тест обработки навигации назад"""
        # Создаем мок Update
        update = Mock()
        update.callback_query = Mock()
        update.callback_query.answer = AsyncMock()
        update.callback_query.message = Mock()
        update.callback_query.message.caption = None
        
        # Добавляем состояния в стек
        self.nav_manager.push_state(self.context, NavStates.MAIN_MENU)
        self.nav_manager.push_state(self.context, NavStates.BUY_MENU)
        
        # Тестируем навигацию назад
        result = await self.nav_manager.handle_back_navigation(update, self.context)
        
        assert result is True
        self.mock_handlers['edit_main_menu'].assert_called_once()
    
    async def test_handle_back_navigation_empty_stack(self):
        """Тест навигации назад с пустым стеком"""
        update = Mock()
        update.callback_query = Mock()
        update.callback_query.answer = AsyncMock()
        update.callback_query.message = Mock()
        update.callback_query.message.caption = None
        
        result = await self.nav_manager.handle_back_navigation(update, self.context)
        
        assert result is True
        self.mock_handlers['edit_main_menu'].assert_called_once()

if __name__ == "__main__":
    # Запуск тестов
    pytest.main([__file__, "-v"])
