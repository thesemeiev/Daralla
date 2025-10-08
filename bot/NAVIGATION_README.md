# 🧭 Система навигации Telegram бота

Централизованная система управления навигацией для Telegram бота с поддержкой стека состояний, валидации переходов и универсальных обработчиков.

## 📁 Структура файлов

```
bot/
├── menu_states.py          # Константы состояний и типов меню
├── navigation.py           # Основная логика навигации
├── menu_handlers.py        # Обработчики всех меню
├── navigation_integration.py # Интеграция с существующим ботом
├── migration_example.py    # Примеры миграции
└── NAVIGATION_README.md    # Документация
```

## 🚀 Быстрый старт

### 1. Импорт и инициализация

```python
from bot.navigation_integration import NavigationIntegration
from bot.menu_states import NavStates, CallbackData

# Создание интеграции
bot_handlers = {
    'edit_main_menu': edit_main_menu,
    'instruction': instruction,
    'mykey': mykey,
    # ... другие обработчики
}

nav_integration = NavigationIntegration(bot_handlers)
```

### 2. Регистрация обработчиков

```python
# В main() функции
app.add_handlers(nav_integration.get_handlers())
```

### 3. Использование в функциях

```python
from bot.navigation import nav_manager, NavigationBuilder

async def my_function(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Добавление состояния в стек
    nav_manager.push_state(context, NavStates.MYKEYS_MENU)
    
    # Создание кнопки "Назад"
    keyboard = NavigationBuilder.create_keyboard_with_back([
        [InlineKeyboardButton("Кнопка 1", callback_data="button1")]
    ])
    
    # Навигация к состоянию
    await nav_manager.navigate_to_state(update, context, NavStates.MAIN_MENU)
```

## 📋 Состояния навигации

### Основные меню
- `MAIN_MENU` - Главное меню
- `INSTRUCTION_MENU` - Меню инструкций
- `BUY_MENU` - Меню покупки
- `MYKEYS_MENU` - Мои ключи
- `POINTS_MENU` - Баллы
- `REFERRAL_MENU` - Рефералы

### Процесс покупки
- `SERVER_SELECTION` - Выбор сервера
- `PAYMENT` - Обработка платежа

### Управление ключами
- `EXTEND_KEY` - Продление ключа
- `RENAME_KEY` - Переименование ключа

### Админ панель
- `ADMIN_MENU` - Админ меню
- `ADMIN_ERRORS` - Логи
- `ADMIN_NOTIFICATIONS` - Уведомления
- `ADMIN_CHECK_SERVERS` - Проверка серверов
- `ADMIN_BROADCAST` - Рассылка
- `ADMIN_SET_DAYS` - Настройка дней

## 🔧 API

### NavigationManager

```python
# Добавление состояния в стек
nav_manager.push_state(context, NavStates.MAIN_MENU)

# Удаление последнего состояния
prev_state = nav_manager.pop_state(context)

# Получение текущего состояния
current = nav_manager.get_current_state(context)

# Очистка стека
nav_manager.clear_stack(context)

# Навигация к состоянию
await nav_manager.navigate_to_state(update, context, NavStates.MAIN_MENU)
```

### NavigationBuilder

```python
# Создание кнопки "Назад"
back_button = NavigationBuilder.create_back_button("Назад")

# Создание кнопки "Главное меню"
main_button = NavigationBuilder.create_main_menu_button("Главное меню")

# Создание клавиатуры с кнопкой "Назад"
keyboard = NavigationBuilder.create_keyboard_with_back([
    [InlineKeyboardButton("Кнопка 1", callback_data="btn1")]
])

# Создание клавиатуры с кнопкой "Главное меню"
keyboard = NavigationBuilder.create_keyboard_with_main_menu([
    [InlineKeyboardButton("Кнопка 1", callback_data="btn1")]
])
```

### NavigationValidator

```python
# Проверка разрешенности перехода
is_allowed = NavigationValidator.validate_state_transition(
    NavStates.MAIN_MENU, 
    NavStates.BUY_MENU
)

# Получение разрешенных переходов
allowed = NavigationValidator.get_allowed_transitions(NavStates.MAIN_MENU)
```

## 🎯 Callback Data

### Основные навигационные кнопки
- `back` - Кнопка "Назад"
- `main_menu` - Кнопка "Главное меню"

### Переходы к меню
- `instruction` - Инструкции
- `buy_vpn` - Купить VPN
- `mykey` - Мои ключи
- `points` - Баллы
- `referral` - Рефералы
- `admin_menu` - Админ панель

### Админ функции
- `admin_errors` - Логи
- `admin_notifications` - Уведомления
- `admin_check_servers` - Проверка серверов
- `admin_broadcast_start` - Рассылка
- `admin_set_days_start` - Настройка дней

## 🔄 Миграция с существующего кода

### 1. Замена функций навигации

```python
# БЫЛО:
def push_nav(context, state):
    stack = context.user_data.setdefault('nav_stack', [])
    stack.append(state)

# СТАЛО:
from bot.navigation import nav_manager
nav_manager.push_state(context, NavStates.MAIN_MENU)
```

### 2. Замена universal_back_callback

```python
# БЫЛО:
async def universal_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 50+ строк кода с elif

# СТАЛО:
from bot.navigation import nav_manager
await nav_manager.handle_back_navigation(update, context)
```

### 3. Обновление кнопок

```python
# БЫЛО:
keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("Кнопка", callback_data="button")],
    [InlineKeyboardButton("Назад", callback_data="back")]
])

# СТАЛО:
from bot.navigation import NavigationBuilder
keyboard = NavigationBuilder.create_keyboard_with_back([
    [InlineKeyboardButton("Кнопка", callback_data="button")]
])
```

## 🐛 Отладка

### Логирование
Система автоматически логирует все операции навигации:
```
PUSH: main_menu -> Stack: ['main_menu']
POP: instruction_menu -> Stack: ['main_menu'] -> Prev: main_menu
🔙 BACK_NAVIGATION: User 123456789
```

### Валидация стека
```python
# Проверка корректности стека
is_valid = nav_manager.validate_stack(context)

# Получение текущего стека
stack = nav_manager.get_stack(context)
print(f"Current stack: {stack}")
```

### Обработка ошибок
```python
try:
    await nav_manager.navigate_to_state(update, context, NavStates.MAIN_MENU)
except Exception as e:
    logger.error(f"Navigation error: {e}")
    # Fallback к главному меню
    await nav_manager.navigate_to_state(update, context, NavStates.MAIN_MENU)
```

## 📈 Преимущества

### ✅ Централизация
- Вся навигация в одном месте
- Единый стиль кода
- Легко найти и исправить проблемы

### ✅ Масштабируемость
- Легко добавлять новые состояния
- Автоматическая валидация переходов
- Константы вместо магических строк

### ✅ Отладка
- Подробное логирование
- Валидация навигационного стека
- Четкие сообщения об ошибках

### ✅ Поддержка
- Документированный код
- Типизация
- Модульная архитектура

### ✅ Производительность
- Меньше дублирования кода
- Оптимизированные переходы
- Кэширование состояний

## 🔮 Планы развития

- [ ] Поддержка истории навигации
- [ ] Breadcrumbs для сложных меню
- [ ] Аналитика навигации
- [ ] A/B тестирование меню
- [ ] Персонализация навигации
- [ ] Поддержка глубоких ссылок
