# 📊 Использование `vpn_keys.db` в проекте

## 🗄️ Структура базы данных

**Файл:** `data/vpn_keys.db`  
**Таблица:** `payments`

**Структура таблицы:**
```sql
CREATE TABLE payments (
    user_id TEXT,              -- ID пользователя Telegram
    payment_id TEXT PRIMARY KEY, -- ID платежа от YooKassa
    status TEXT,               -- pending, succeeded, failed, canceled, refunded
    created_at INTEGER,        -- Unix timestamp создания
    meta TEXT,                 -- JSON с мета-данными (period, price, type и т.д.)
    activated INTEGER DEFAULT 0 -- 0 или 1 (обработан ли платеж)
)
```

---

## 🔧 Функции работы с `vpn_keys.db`

### 1. Инициализация

**Функция:** `init_payments_db()`  
**Файл:** `bot/db/keys_db.py`  
**Вызывается:** `bot/core/startup.py` → `init_all_db()`

**Что делает:**
- Создает таблицу `payments`, если её нет
- Вызывается при старте бота

---

### 2. Создание платежа

**Функция:** `add_payment(user_id, payment_id, status, created_at, meta)`  
**Файл:** `bot/db/keys_db.py`  
**Используется в:**
- `bot/handlers/payments/payment_handler.py` - создание платежа при покупке

**Что делает:**
- Сохраняет платеж в БД со статусом `'pending'`
- Сохраняет мета-данные (period, price, type, unique_email и т.д.)

**Пример использования:**
```python
# bot/handlers/payments/payment_handler.py:244
await add_payment(
    user_id=user_id,
    payment_id=payment.id,
    status='pending',
    created_at=now,
    meta=payment_meta  # {type, price, unique_email, message_id}
)
```

---

### 3. Получение платежа

#### 3.1. По user_id

**Функция:** `get_payment(user_id)`  
**Файл:** `bot/db/keys_db.py`  
**Используется в:**
- Не используется напрямую (возможно, в старой логике)

**Что делает:**
- Возвращает последний платеж пользователя

---

#### 3.2. По payment_id (для webhook'ов)

**Функция:** `get_payment_by_id(payment_id)`  
**Файл:** `bot/db/keys_db.py`  
**Используется в:**
- `bot/handlers/webhooks/payment_processors.py` - обработка webhook'ов от YooKassa
- `bot/handlers/admin/admin_test_payment.py` - тестовые платежи

**Что делает:**
- Получает платеж по ID (используется в webhook'ах)

**Пример использования:**
```python
# bot/handlers/webhooks/payment_processors.py:42
payment_info = await get_payment_by_id(payment_id)
if not payment_info:
    logger.warning(f"Платеж {payment_id} не найден в базе данных")
    return
```

---

#### 3.3. Pending платеж по user_id и period

**Функция:** `get_pending_payment(user_id, period)`  
**Файл:** `bot/db/keys_db.py`  
**Используется в:**
- `bot/handlers/payments/payment_handler.py` - проверка существующего pending платежа
- `bot/handlers/admin/admin_test_payment.py` - тестовые платежи

**Что делает:**
- Проверяет, есть ли у пользователя pending платеж для данного периода

**Пример использования:**
```python
# bot/handlers/payments/payment_handler.py:109
existing_payment = await get_pending_payment(user_id, period)
if existing_payment:
    # Используем существующий платеж
```

---

#### 3.4. Все pending платежи

**Функция:** `get_all_pending_payments()`  
**Файл:** `bot/db/keys_db.py`  
**Используется в:**
- `bot/handlers/admin/admin_test_payment.py` - админ-панель

**Что делает:**
- Возвращает все pending платежи (для админ-панели)

---

### 4. Обновление статуса платежа

**Функция:** `update_payment_status(payment_id, status)`  
**Файл:** `bot/db/keys_db.py`  
**Используется в:**
- `bot/handlers/webhooks/payment_processors.py` - обновление статуса после webhook'а

**Что делает:**
- Обновляет статус платежа (pending → succeeded/failed/canceled)

**Пример использования:**
```python
# bot/handlers/webhooks/payment_processors.py:270
await update_payment_status(payment_id, 'succeeded')
```

**Где используется:**
- ✅ `process_extension_payment()` - успешное продление
- ✅ `process_new_purchase_payment()` - успешная покупка
- ✅ `process_canceled_payment()` - отмененный платеж
- ✅ `process_failed_payment()` - неудачный платеж
- ✅ Обработка ошибок (статус → 'failed')

---

### 5. Обновление активации платежа

**Функция:** `update_payment_activation(payment_id, activated)`  
**Файл:** `bot/db/keys_db.py`  
**Используется в:**
- `bot/handlers/webhooks/payment_processors.py` - отметка обработки платежа

**Что делает:**
- Устанавливает флаг `activated` (0 или 1)
- Защита от повторной обработки webhook'ов

**Пример использования:**
```python
# bot/handlers/webhooks/payment_processors.py:271
await update_payment_activation(payment_id, 1)  # Платеж обработан
```

**Где используется:**
- ✅ После успешной обработки платежа (activated = 1)
- ✅ При отмене платежа (activated = 0)

---

### 6. Очистка старых платежей

#### 6.1. Очистка старых записей

**Функция:** `cleanup_old_payments(days_old=7)`  
**Файл:** `bot/db/keys_db.py`  
**Используется в:**
- `bot/core/tasks.py` - периодическая очистка (каждый час)

**Что делает:**
- Удаляет старые записи платежей (старше 7 дней)
- Удаляет только завершенные платежи (succeeded, canceled, refunded)

**Пример использования:**
```python
# bot/core/tasks.py:62
old_count = await cleanup_old_payments(days_old=7)
```

---

#### 6.2. Очистка просроченных pending платежей

**Функция:** `cleanup_expired_pending_payments(minutes_old=20)`  
**Файл:** `bot/db/keys_db.py`  
**Используется в:**
- `bot/core/tasks.py` - периодическая очистка (каждый час)

**Что делает:**
- Удаляет pending платежи старше 20 минут
- Пользователь не оплатил в течение 20 минут → платеж удаляется

**Пример использования:**
```python
# bot/core/tasks.py:57
expired_count = await cleanup_expired_pending_payments(minutes_old=20)
```

---

## 📍 Где используется `vpn_keys.db`

### 1. Создание платежа

**Файл:** `bot/handlers/payments/payment_handler.py`

```python
# Строка 244
await add_payment(user_id, payment.id, 'pending', now, payment_meta)
```

**Когда:** Пользователь выбирает период и создается платеж в YooKassa

---

### 2. Обработка webhook'ов

**Файл:** `bot/handlers/webhooks/payment_processors.py`

**Используемые функции:**
- `get_payment_by_id()` - получение платежа (строки 42, 623)
- `update_payment_status()` - обновление статуса (множество мест)
- `update_payment_activation()` - отметка обработки (строки 271, 539, 691, 728)

**Когда:** YooKassa отправляет webhook о статусе платежа

---

### 3. Периодическая очистка

**Файл:** `bot/core/tasks.py`

**Используемые функции:**
- `cleanup_expired_pending_payments()` - очистка просроченных pending (строка 57)
- `cleanup_old_payments()` - очистка старых записей (строка 62)

**Когда:** Каждый час автоматически

---

### 4. Админ-панель

**Файл:** `bot/handlers/admin/admin_test_payment.py`

**Используемые функции:**
- `get_pending_payment()` - проверка существующего платежа
- `get_all_pending_payments()` - список всех pending платежей
- `get_payment_by_id()` - получение платежа по ID

**Когда:** Админ использует тестовые платежи

---

## 🔄 Полный цикл использования

```
1. Пользователь выбирает период
   ↓
2. handle_payment() создает платеж в YooKassa
   ↓
3. add_payment() сохраняет в vpn_keys.db (status: 'pending')
   ↓
4. Пользователь оплачивает
   ↓
5. YooKassa отправляет webhook
   ↓
6. process_payment_webhook() получает webhook
   ↓
7. get_payment_by_id() получает платеж из vpn_keys.db
   ↓
8. Обработка платежа (создание/продление подписки)
   ↓
9. update_payment_status() обновляет статус ('succeeded')
   ↓
10. update_payment_activation() отмечает как обработанный (activated=1)
   ↓
11. cleanup_old_payments_task() периодически очищает старые записи
```

---

## 📊 Статистика использования

### Функции (всего 9):

1. ✅ `init_payments_db()` - инициализация
2. ✅ `add_payment()` - создание платежа
3. ✅ `get_payment()` - получение по user_id (не используется)
4. ✅ `get_payment_by_id()` - получение по payment_id (webhook'и)
5. ✅ `get_pending_payment()` - проверка pending платежа
6. ✅ `get_all_pending_payments()` - все pending (админ)
7. ✅ `update_payment_status()` - обновление статуса
8. ✅ `update_payment_activation()` - отметка обработки
9. ✅ `cleanup_old_payments()` - очистка старых
10. ✅ `cleanup_expired_pending_payments()` - очистка просроченных

### Файлы, использующие `vpn_keys.db`:

1. ✅ `bot/db/keys_db.py` - определение функций
2. ✅ `bot/handlers/payments/payment_handler.py` - создание платежа
3. ✅ `bot/handlers/webhooks/payment_processors.py` - обработка webhook'ов
4. ✅ `bot/core/tasks.py` - периодическая очистка
5. ✅ `bot/handlers/admin/admin_test_payment.py` - админ-панель
6. ✅ `bot/core/startup.py` - инициализация

---

## ✅ Вывод

**`vpn_keys.db` активно используется** для:
- ✅ Хранения всех платежей (pending, succeeded, failed и т.д.)
- ✅ Обработки webhook'ов от YooKassa
- ✅ Защиты от повторной обработки (флаг `activated`)
- ✅ Очистки старых данных

**Название `vpn_keys.db` вводит в заблуждение** - это БД для платежей, а не для ключей.  
**Рекомендация:** Переименовать в `payments.db` (но это требует изменений в коде).

---

## 🔧 Как переименовать (если нужно)

1. Переименовать файл: `vpn_keys.db` → `payments.db`
2. Обновить `DB_PATH` в `bot/db/keys_db.py`:
   ```python
   DB_PATH = os.path.join(DATA_DIR, 'payments.db')  # было: 'vpn_keys.db'
   ```
3. Обновить комментарии и документацию

**Но это не критично** - функционально все работает правильно!

