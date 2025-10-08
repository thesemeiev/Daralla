"""
Пример миграции существующего бота на новую систему навигации
"""

# ===== ДО (старый код в bot.py) =====

# Старые функции навигации
def push_nav(context, state, max_size=10):
    stack = context.user_data.setdefault('nav_stack', [])
    if len(stack) >= max_size:
        stack.pop(0)
    stack.append(state)
    logger.info(f"PUSH: {state} -> Stack: {stack}")

def pop_nav(context):
    stack = context.user_data.get('nav_stack', [])
    if stack:
        popped = stack.pop()
        logger.info(f"POP: {popped} -> Stack: {stack}")
        return stack[-1] if stack else None
    logger.info(f"POP: empty stack")
    return None

async def universal_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    prev_state = pop_nav(context)
    
    if prev_state is None:
        await start(update, context)
    elif prev_state == 'main_menu':
        await edit_main_menu(update, context)
    elif prev_state == 'instruction_menu':
        await instruction(update, context)
    # ... много других elif
    else:
        await start(update, context)

# ===== ПОСЛЕ (новый код) =====

# 1. Импорты в начале bot.py
from .navigation_integration import NavigationIntegration
from .menu_states import NavStates, CallbackData

# 2. Создание интеграции после определения всех обработчиков
def setup_navigation():
    """Настройка системы навигации"""
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
    
    return NavigationIntegration(bot_handlers)

# 3. В main() функции
def main():
    # ... существующий код ...
    
    # Создаем интеграцию навигации
    nav_integration = setup_navigation()
    
    # Добавляем новые обработчики
    app.add_handlers(nav_integration.get_handlers())
    
    # ... остальной код ...

# 4. Обновление существующих функций
async def instruction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_private_chat(update):
        return
    
    # ЗАМЕНИТЬ:
    # if not context.user_data.get('nav_stack'):
    #     context.user_data['nav_stack'] = ['main_menu']
    # stack = context.user_data['nav_stack']
    # if not stack or stack[-1] != 'instruction_menu':
    #     push_nav(context, 'instruction_menu')
    
    # НА:
    from .navigation import nav_manager
    nav_manager.push_state(context, NavStates.INSTRUCTION_MENU)
    
    # ... остальной код ...

# 5. Обновление кнопок
def create_instruction_keyboard():
    # ЗАМЕНИТЬ:
    # keyboard = InlineKeyboardMarkup([
    #     [InlineKeyboardButton("Android", callback_data="instr_android"), InlineKeyboardButton("iOS", callback_data="instr_ios")],
    #     [InlineKeyboardButton("Windows", callback_data="instr_windows"), InlineKeyboardButton("macOS", callback_data="instr_macos")],
    #     [InlineKeyboardButton("Linux", callback_data="instr_linux"), InlineKeyboardButton("Android TV", callback_data="instr_tv")],
    #     [InlineKeyboardButton("FAQ", callback_data="instr_faq")],
    #     [UIButtons.back_button()],
    # ])
    
    # НА:
    from .navigation import NavigationBuilder
    buttons = [
        [InlineKeyboardButton("Android", callback_data="instr_android"), InlineKeyboardButton("iOS", callback_data="instr_ios")],
        [InlineKeyboardButton("Windows", callback_data="instr_windows"), InlineKeyboardButton("macOS", callback_data="instr_macos")],
        [InlineKeyboardButton("Linux", callback_data="instr_linux"), InlineKeyboardButton("Android TV", callback_data="instr_tv")],
        [InlineKeyboardButton("FAQ", callback_data="instr_faq")],
    ]
    return NavigationBuilder.create_keyboard_with_back(buttons)

# 6. Удаление старых функций
# УДАЛИТЬ:
# - push_nav()
# - pop_nav() 
# - universal_back_callback()
# - Все старые CallbackQueryHandler для навигации

# 7. Обновление регистрации обработчиков
def register_handlers(app):
    # УДАЛИТЬ старые обработчики:
    # app.add_handler(CallbackQueryHandler(universal_back_callback, pattern="^back$"))
    # app.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"))
    
    # ДОБАВИТЬ новые:
    nav_integration = setup_navigation()
    app.add_handlers(nav_integration.get_handlers())

# ===== ПРЕИМУЩЕСТВА НОВОЙ СИСТЕМЫ =====

"""
1. ЦЕНТРАЛИЗАЦИЯ
   - Вся навигация в одном месте
   - Легко найти и исправить проблемы
   - Единый стиль кода

2. МАСШТАБИРУЕМОСТЬ
   - Легко добавлять новые состояния
   - Автоматическая валидация переходов
   - Константы вместо магических строк

3. ОТЛАДКА
   - Подробное логирование
   - Валидация навигационного стека
   - Четкие сообщения об ошибках

4. ПОДДЕРЖКА
   - Документированный код
   - Типизация
   - Модульная архитектура

5. ПРОИЗВОДИТЕЛЬНОСТЬ
   - Меньше дублирования кода
   - Оптимизированные переходы
   - Кэширование состояний
"""
