# 📚 Простое руководство по проекту Daralla VPN Bot

## 🎯 Для кого это руководство

Это руководство для тех, кто хочет понять, как работает проект, но не имеет глубоких знаний в программировании. Здесь все объяснено простым языком с примерами.

---

## 📦 Что делает этот бот?

Бот продает VPN-подписки через Telegram. Пользователь:
1. Выбирает период (1 месяц или 3 месяца)
2. Оплачивает через YooKassa
3. Получает ссылку на подписку
4. Использует эту ссылку в VPN-клиенте

---

## 🗄️ Как работает база данных

### Что такое база данных?

База данных (БД) - это файлы, где хранится вся информация:
- Кто купил подписку
- Когда она истекает
- Какие платежи были
- Какие уведомления отправлены

### Какие базы данных есть?

В проекте **4 базы данных** (все в папке `data/`):

**⚠️ Важно:** Две БД (`vpn_keys.db` и `users.db`) из старой архитектуры с ключами, но все еще используются. Две новые БД (`subscribers.db` и `notifications.db`) для новой архитектуры с подписками.

#### 1. `vpn_keys.db` - Платежи ⚠️ (старая архитектура, но используется)
**Что хранит:**
- Таблица `payments` - все платежи (успешные, отмененные, pending)

**Пример:**
```
Платеж ID: abc123
├─ Статус: succeeded (успешно)
├─ Пользователь: 123456789
├─ Сумма: 150₽
└─ Период: month (1 месяц)
```

#### 2. `users.db` - Пользователи и конфигурация ⚠️ (старая архитектура, но используется)
**Что хранит:**
- Таблица `users` - список всех пользователей
- Таблица `config` - настройки бота

**Пример:**
```
Пользователь ID: 123456789
├─ first_seen: 01.01.2024
└─ last_seen: 15.01.2025

Конфигурация:
├─ key: "admin_notifications"
└─ value: "enabled"
```

#### 3. `notifications.db` - Уведомления ✅ (новая архитектура)
**Что хранит:**
- Какие уведомления отправлены (чтобы не спамить)
- Эффективность уведомлений (кто продлил после уведомления)

**Пример:**
```
Подписка ID: 5
├─ Уведомление "истекает через 3 дня" - отправлено 01.01.2025
├─ Уведомление "истекает через 1 день" - отправлено 03.01.2025
└─ Уведомление "истекает через 1 час" - не отправлено (продлена)
```

#### 4. `subscribers.db` - Подписки ✅ (новая архитектура)
**Что хранит:**
- Таблица `subscribers` - пользователи Telegram
- Таблица `subscriptions` - подписки пользователей
- Таблица `subscription_servers` - связь подписки с серверами

**Пример:**
```
Пользователь ID: 123456789
├─ Подписка 1: "Для мамы" (активна до 01.01.2025)
├─ Подписка 2: "Для друга" (активна до 15.01.2025)
└─ Подписка 3: "Рабочая" (истекла)
```

**Простое объяснение:**

1. **При старте бота:**
   ```python
   # bot/core/startup.py
   await init_all_db()  # Создает все таблицы, если их нет
   ```

2. **При создании подписки:**
   ```python
   # bot/services/subscription_manager.py
   subscription_id, token = await create_subscription(...)  # Записывает в БД
   ```

3. **При проверке подписки:**
   ```python
   # bot/db/subscribers_db.py
   sub = await get_subscription_by_token(token)  # Читает из БД
   ```

**Важно:** Бот использует `aiosqlite` - это библиотека для работы с SQLite (простая БД в файле).

---

## 💳 Как проходят платежи (полный цикл)

### Шаг 1: Пользователь выбирает период

```
Пользователь нажимает "Купить VPN" 
  ↓
Бот показывает: "1 месяц - 150₽" или "3 месяца - 350₽"
  ↓
Пользователь выбирает период
```

**Код:** `bot/handlers/callbacks/payment_callbacks.py`

---

### Шаг 2: Создание платежа

```
Бот создает платеж в YooKassa
  ↓
YooKassa возвращает ссылку на оплату
  ↓
Бот сохраняет платеж в БД со статусом 'pending'
  ↓
Бот отправляет пользователю ссылку на оплату
```

**Что происходит в коде:**

```python
# bot/handlers/payments/payment_handler.py
payment = Payment.create({
    "amount": {"value": price, "currency": "RUB"},
    "metadata": {
        "user_id": user_id,
        "type": period,  # "month" или "3month"
        "price": price
    }
})

# Сохраняем в БД
await add_payment(user_id, payment.id, 'pending', now, payment_meta)
```

**Файлы:**
- `bot/handlers/payments/payment_handler.py` - создание платежа
- `bot/db/keys_db.py` - сохранение в БД

---

### Шаг 3: Пользователь оплачивает

```
Пользователь переходит по ссылке
  ↓
Оплачивает через YooKassa (карта, СБП и т.д.)
  ↓
YooKassa обрабатывает платеж
```

**Это происходит вне бота** - на стороне YooKassa.

---

### Шаг 4: YooKassa отправляет webhook

```
YooKassa отправляет POST запрос на /webhook/yookassa
  ↓
Статус платежа: 'succeeded' (успешно)
  ↓
Бот получает webhook и обрабатывает его
```

**Что происходит в коде:**

```python
# bot/handlers/webhooks/webhook_app.py
@app.route('/webhook/yookassa', methods=['POST'])
def yookassa_webhook():
    payment_id = request.json['object']['id']
    status = request.json['object']['status']
    
    # Обрабатываем платеж
    await process_payment_webhook(bot_app, payment_id, status)
```

**Файлы:**
- `bot/handlers/webhooks/webhook_app.py` - Flask сервер для webhook
- `bot/handlers/webhooks/payment_processors.py` - обработка платежа

---

### Шаг 5: Создание подписки

```
Бот проверяет: платеж уже обработан?
  ↓ (нет)
Бот создает подписку в БД (subscriptions)
  ↓
Бот генерирует уникальный токен (например: abc123xyz)
  ↓
Бот привязывает ВСЕ серверы к подписке
  ↓
Бот создает клиентов на доступных серверах X-UI
  ↓
Бот отправляет пользователю ссылку: /sub/{token}
```

**Что происходит в коде:**

```python
# bot/handlers/webhooks/payment_processors.py
async def process_new_purchase_payment(...):
    # 1. Создаем подписку в БД
    sub_dict, token = await subscription_manager.create_subscription_for_user(
        user_id=user_id,
        period=period,
        device_limit=1,
        price=price
    )
    
    # 2. Привязываем все серверы
    for server_name in all_servers:
        await subscription_manager.attach_server_to_subscription(
            subscription_id=sub_dict['id'],
            server_name=server_name
        )
    
    # 3. Создаем клиентов на серверах
    for server_name in available_servers:
        await subscription_manager.ensure_client_on_server(...)
    
    # 4. Отправляем ссылку пользователю
    subscription_url = f"{base_url}/sub/{token}"
    await bot.send_message(user_id, f"Ваша подписка: {subscription_url}")
```

**Файлы:**
- `bot/handlers/webhooks/payment_processors.py` - `process_new_purchase_payment()`
- `bot/services/subscription_manager.py` - создание подписки

---

### Шаг 6: Пользователь использует подписку

```
VPN-клиент запрашивает: GET /sub/{token}
  ↓
Бот проверяет токен в БД
  ↓
Бот проверяет: подписка активна? не истекла?
  ↓ (да)
Бот генерирует VLESS ссылки для всех серверов
  ↓
Бот отправляет ссылки клиенту
```

**Что происходит в коде:**

```python
# bot/handlers/webhooks/webhook_app.py
@app.route('/sub/<token>', methods=['GET'])
def subscription(token):
    # Проверяем токен
    sub = await get_subscription_by_token(token)
    if not sub or sub['status'] != 'active':
        return "Подписка не найдена или истекла", 404
    
    # Генерируем ссылки
    links = await subscription_manager.build_vless_links_for_subscription(sub['id'])
    
    # Отправляем клиенту
    return "\n".join(links)
```

**Файлы:**
- `bot/handlers/webhooks/webhook_app.py` - эндпоинт `/sub/{token}`
- `bot/services/subscription_manager.py` - генерация VLESS ссылок

---

## 🔄 Фоновые задачи (автоматические процессы)

### Что такое фоновые задачи?

Это процессы, которые работают **автоматически** в фоне, пока бот работает. Они запускаются при старте бота и работают постоянно.

### Какие задачи есть?

#### 1. Очистка старых данных (`cleanup_old_payments_task`)

**Что делает:**
- Удаляет просроченные pending платежи (старше 20 минут)
- Удаляет старые записи платежей (старше 7 дней)
- Обновляет статус истекших подписок (active → expired)

**Как часто:** Каждый час

**Код:**
```python
# bot/core/tasks.py
async def cleanup_old_payments_task():
    while True:
        # Очищаем просроченные pending платежи
        await cleanup_expired_pending_payments(minutes_old=20)
        
        # Очищаем старые записи
        await cleanup_old_payments(days_old=7)
        
        # Обновляем истекшие подписки
        await cleanup_expired_subscriptions()
        
        # Ждем 1 час
        await asyncio.sleep(3600)
```

**Запуск:** `bot/core/startup.py` → `asyncio.create_task(cleanup_old_payments_task())`

---

#### 2. Синхронизация БД с X-UI (`sync_db_with_xui_task`)

**Что делает:**
- Проверяет все активные подписки
- Для каждой подписки проверяет: есть ли клиент на сервере?
- Если клиента нет - создает его
- Если клиент есть, но истек - продлевает
- Ищет "orphaned" клиентов (есть на сервере, но нет в БД)

**Как часто:** Каждые 6 часов

**Код:**
```python
# bot/core/tasks.py
async def sync_db_with_xui_task():
    while True:
        # Ждем 6 часов
        await asyncio.sleep(6 * 60 * 60)
        
        # Синхронизируем все подписки
        stats = await sync_manager.sync_all_subscriptions()
        
        # Ищем orphaned клиентов
        orphaned = await sync_manager.find_orphaned_clients()
```

**Запуск:** `bot/core/startup.py` → `asyncio.create_task(sync_db_with_xui_task())`

---

#### 3. Синхронизация серверов с конфигурацией (`sync_servers_with_config_task`)

**Что делает:**
- Проверяет: какие серверы есть в конфигурации?
- Для каждой подписки:
  - Добавляет новые серверы (если добавили в конфиг)
  - Удаляет старые серверы (если удалили из конфига)
  - Создает клиентов на новых серверах

**Как часто:** Каждый час

**Код:**
```python
# bot/core/tasks.py
async def sync_servers_with_config_task():
    while True:
        # Ждем 1 час
        await asyncio.sleep(60 * 60)
        
        # Синхронизируем серверы
        stats = await subscription_manager.sync_servers_with_config(
            auto_create_clients=True
        )
```

**Запуск:** `bot/core/startup.py` → `asyncio.create_task(sync_servers_with_config_task())`

---

#### 4. Уведомления об истечении (`NotificationManager`)

**Что делает:**
- Проверяет все активные подписки
- Определяет: сколько дней до истечения?
- Отправляет уведомления:
  - За 3 дня до истечения
  - За 1 день до истечения
  - За 1 час до истечения
- Защита от спама: проверяет БД, отправляли ли уже это уведомление?

**Как часто:** Каждые 5 минут

**Код:**
```python
# bot/services/notification_manager.py
async def check_expiring_keys():
    while True:
        # Проверяем подписки
        await self._check_expiring_subscriptions()
        
        # Ждем 5 минут
        await asyncio.sleep(5 * 60)
```

**Запуск:** `bot/core/startup.py` → `await notification_manager.start()`

---

#### 5. Мониторинг серверов (`server_health_monitor`)

**Что делает:**
- Проверяет доступность всех серверов X-UI
- Если сервер недоступен - отправляет уведомление админу
- Если сервер восстановился - отправляет уведомление админу

**Как часто:** Каждые 5 минут

**Код:**
```python
# bot/core/startup.py
async def server_health_monitor(app):
    while True:
        # Проверяем серверы
        health_results = server_manager.check_all_servers_health()
        
        # Отправляем уведомления при изменении статуса
        ...
        
        # Ждем 5 минут
        await asyncio.sleep(300)
```

**Запуск:** `bot/core/startup.py` → `asyncio.create_task(server_health_monitor(app))`

---

## 🏗️ Общая архитектура проекта

### Структура проекта

```
bot/
├── bot.py                    # Главный файл - запуск бота
├── core/                     # Ядро системы
│   ├── startup.py           # Инициализация при старте
│   └── tasks.py             # Фоновые задачи
├── handlers/                 # Обработчики событий
│   ├── commands/            # Команды (/start, /mykey)
│   ├── callbacks/           # Обработчики кнопок
│   ├── payments/            # Создание платежей
│   ├── webhooks/            # Webhook от YooKassa
│   └── admin/               # Админ-панель
├── services/                 # Бизнес-логика
│   ├── subscription_manager.py  # Управление подписками
│   ├── server_manager.py    # Управление серверами
│   ├── sync_manager.py      # Синхронизация
│   └── notification_manager.py  # Уведомления
├── db/                       # Работа с БД
│   ├── subscribers_db.py      # Подписки
│   ├── keys_db.py          # Платежи
│   └── notifications_db.py # Уведомления
└── navigation/              # Система навигации
```

---

### Как все работает вместе?

```
1. Запуск бота (bot.py)
   ↓
2. Инициализация (startup.py)
   ├─ Инициализация БД
   ├─ Инициализация менеджеров
   └─ Запуск фоновых задач
   ↓
3. Бот работает
   ├─ Обрабатывает команды пользователей
   ├─ Обрабатывает платежи
   ├─ Обрабатывает webhook'и
   └─ Фоновые задачи работают автоматически
```

---

## ✅ Вы делаете все правильно?

### Давайте проверим:

#### ✅ Правильно:
1. **Используете централизованные константы** (`CallbackData`, `UIEmojis`)
2. **Следуете архитектуре** (Saga Pattern, Repository Pattern)
3. **Используете менеджеры** (`SubscriptionManager`, `NotificationManager`)
4. **Правильная работа с БД** (async/await, транзакции)

#### ⚠️ На что обратить внимание:

1. **Не дублируйте код** - используйте существующие функции
2. **Проверяйте ошибки** - всегда обрабатывайте исключения
3. **Логируйте действия** - используйте `logger.info()`, `logger.error()`
4. **Тестируйте изменения** - проверяйте работу после изменений

---

## 🎓 Полезные советы

### Как найти, где что происходит?

1. **Покупка подписки:**
   - `bot/handlers/payments/payment_handler.py` - создание платежа
   - `bot/handlers/webhooks/payment_processors.py` - обработка webhook

2. **Работа с подписками:**
   - `bot/services/subscription_manager.py` - создание, продление
   - `bot/db/subscribers_db.py` - работа с БД

3. **Уведомления:**
   - `bot/services/notification_manager.py` - логика уведомлений
   - `bot/db/notifications_db.py` - БД уведомлений

4. **Фоновые задачи:**
   - `bot/core/tasks.py` - все фоновые задачи
   - `bot/core/startup.py` - запуск задач

### Как добавить новую функцию?

1. **Определите, куда она относится:**
   - Работа с БД → `bot/db/`
   - Бизнес-логика → `bot/services/`
   - Обработка событий → `bot/handlers/`

2. **Следуйте существующим паттернам:**
   - Используйте async/await
   - Используйте менеджеры
   - Логируйте действия

3. **Тестируйте:**
   - Проверьте работу функции
   - Проверьте обработку ошибок
   - Проверьте логи

---

## 📝 Резюме

### Что вы должны понимать:

1. **БД:** 4 базы данных, все в `data/`, работа через `aiosqlite`
2. **Платежи:** Пользователь → YooKassa → Webhook → Создание подписки
3. **Фоновые задачи:** 5 задач, работают автоматически
4. **Архитектура:** Менеджеры, обработчики, БД - все разделено по модулям

### Вы делаете все правильно, если:

- ✅ Используете существующие функции
- ✅ Следуете архитектуре
- ✅ Логируете действия
- ✅ Обрабатываете ошибки

**Продолжайте в том же духе!** 🚀

