# Места проверки доступности серверов

## Дата: 2024-12-14

## Все места, где проверяется доступность серверов

### 1. ✅ Фоновый мониторинг (периодический)
**Файл:** `bot/core/startup.py:126`
**Метод:** `server_health_monitor()`
**Частота:** Каждые 5 минут
**Метод проверки:** `check_all_servers_health(force_check=False)`
**Количество попыток:** 1 на сервер (использует кэш)
**Статус:** ✅ Оптимизировано

```python
health_results = server_manager.check_all_servers_health(force_check=False)
```

---

### 2. ✅ Команда "Мои ключи" (/mykey)
**Файл:** `bot/handlers/commands/mykey_handler.py:85`
**Метод:** `mykey()`
**Триггер:** Пользователь нажимает "Мои ключи"
**Метод проверки:** `check_server_health()` для каждого сервера + `list_quick()` для получения ключей
**Количество попыток:** 1 на сервер (использует кэш + list_quick)
**Статус:** ✅ Оптимизировано

```python
# Проверка через кэш
is_healthy = server_manager.check_server_health(server_name, force_check=False)
# Получение списка ключей
inbounds = xui.list_quick()['obj']
```

---

### 3. ✅ Меню выбора сервера
**Файл:** `bot/navigation/menu_handlers.py:99`
**Метод:** `server_selection()`
**Триггер:** Пользователь выбирает сервер при покупке
**Метод проверки:** `check_all_servers_health(force_check=False)`
**Количество попыток:** 1 на сервер (использует кэш)
**Статус:** ✅ Оптимизировано

```python
health_results = new_client_manager.check_all_servers_health(force_check=False)
```

---

### 4. ⚠️ Создание платежа (перед покупкой)
**Файл:** `bot/handlers/payments/payment_handler.py:70, 76`
**Метод:** `handle_payment()`
**Триггер:** Пользователь выбирает период и создает платеж
**Метод проверки:** `check_server_health()` для каждого сервера в цикле
**Количество попыток:** 1 на сервер (использует кэш)
**Проблема:** Проверяет каждый сервер отдельно в цикле, но использует кэш
**Статус:** ⚠️ Можно оптимизировать

```python
for server in servers:
    if new_client_manager.check_server_health(server["name"]):
        available_servers += 1
```

**Рекомендация:** Использовать `check_all_servers_health()` один раз вместо цикла

---

### 5. ⚠️ Callback обработчики платежей
**Файл:** `bot/handlers/callbacks/payment_callbacks.py:103, 120`
**Метод:** `handle_payment_callback()`
**Триггер:** Пользователь выбирает локацию/сервер
**Метод проверки:** `check_server_health()` для каждого сервера в цикле
**Количество попыток:** 1 на сервер (использует кэш)
**Проблема:** Проверяет каждый сервер отдельно в цикле
**Статус:** ⚠️ Можно оптимизировать

```python
for server in servers:
    if new_client_manager.check_server_health(server["name"]):
        # ...
```

**Рекомендация:** Использовать `check_all_servers_health()` один раз

---

### 6. ✅ Админ панель - проверка серверов
**Файл:** `bot/handlers/admin/admin_check_servers.py:61, 189-190`
**Метод:** `admin_check_servers()`, `force_check_servers()`
**Триггер:** Админ нажимает "Проверить серверы"
**Метод проверки:** `check_all_servers_health(force_check=True)`
**Количество попыток:** 1 на сервер (принудительная проверка, обходит кэш)
**Статус:** ✅ Корректно (админ хочет актуальный статус)

```python
# Обычная проверка
health_results = server_manager.check_all_servers_health(force_check=True)
# Принудительная проверка
health_results = server_manager.check_all_servers_health(force_check=True)
new_client_health = new_client_manager.check_all_servers_health(force_check=True)
```

**Примечание:** В `force_check_servers()` проверяются оба менеджера, но это для админа, поэтому допустимо

---

### 7. ✅ Очистка просроченных ключей
**Файл:** `bot/core/tasks.py:140, 159`
**Метод:** `auto_cleanup_expired_keys()`
**Частота:** Периодически
**Метод проверки:** `check_server_health()` для каждого сервера
**Количество попыток:** 1 на сервер (использует кэш)
**Статус:** ✅ Оптимизировано

```python
if server_manager.check_server_health(server["name"]):
    # Очистка ключей
```

---

### 8. ✅ Проверка истекающих ключей (уведомления)
**Файл:** `bot/services/notification_manager.py:178`
**Метод:** `check_expiring_keys()`
**Частота:** Периодически
**Метод проверки:** `check_server_health()` для каждого сервера
**Количество попыток:** 1 на сервер (использует кэш)
**Статус:** ✅ Оптимизировано

```python
if not self.server_manager.check_server_health(server["name"]):
    continue
```

---

## Итоговая статистика

### Всего мест проверки: 8

**✅ Полностью оптимизировано (1 попытка):** 6 мест
- Фоновый мониторинг
- Команда "Мои ключи"
- Меню выбора сервера
- Админ панель
- Очистка просроченных ключей
- Проверка истекающих ключей

**⚠️ Можно оптимизировать (1 попытка, но неэффективно):** 2 места
- Создание платежа (проверяет в цикле)
- Callback обработчики платежей (проверяет в цикле)

## Рекомендации по оптимизации

### 1. Оптимизация создания платежа
**Текущий код:**
```python
for server in servers:
    if new_client_manager.check_server_health(server["name"]):
        available_servers += 1
```

**Рекомендуемый код:**
```python
# Проверяем все серверы один раз
all_health = new_client_manager.check_all_servers_health(force_check=False)
for server in servers:
    if all_health.get(server["name"], False):
        available_servers += 1
```

### 2. Оптимизация callback обработчиков
**Текущий код:**
```python
for server in servers:
    if new_client_manager.check_server_health(server["name"]):
        # ...
```

**Рекомендуемый код:**
```python
# Проверяем все серверы один раз
all_health = new_client_manager.check_all_servers_health(force_check=False)
for server in servers:
    if all_health.get(server["name"], False):
        # ...
```

## Заключение

**Текущее состояние:**
- ✅ Большинство мест уже оптимизировано (1 попытка на сервер)
- ⚠️ 2 места можно улучшить (использовать `check_all_servers_health()` вместо цикла)

**Общий результат:**
- Все проверки используют кэш (TTL = 30 сек)
- Circuit Breaker активен (после 3 неудач - 5 минут cooldown)
- Большинство проверок делают 1 попытку на сервер

