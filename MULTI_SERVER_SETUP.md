# Настройка дополнительных серверов

## Обзор

Теперь бот поддерживает по 2 сервера для каждой локации:
- **Finland-1** и **Finland-2**
- **Latvia-1** и **Latvia-2** 
- **Estonia-1** и **Estonia-2**

## Настройка .env файла

Добавьте следующие переменные в ваш `.env` файл:

```bash
# Finland серверы
XUI_HOST_FINLAND_1=https://finland-1.chechen-community.online
XUI_LOGIN_FINLAND_1=your_finland_1_username
XUI_PASSWORD_FINLAND_1=your_finland_1_password

XUI_HOST_FINLAND_2=https://finland-2.chechen-community.online
XUI_LOGIN_FINLAND_2=your_finland_2_username
XUI_PASSWORD_FINLAND_2=your_finland_2_password

# Latvia серверы
XUI_HOST_LATVIA_1=https://latvia-1.chechen-community.online
XUI_LOGIN_LATVIA_1=your_latvia_1_username
XUI_PASSWORD_LATVIA_1=your_latvia_1_password

XUI_HOST_LATVIA_2=https://latvia-2.chechen-community.online
XUI_LOGIN_LATVIA_2=your_latvia_2_username
XUI_PASSWORD_LATVIA_2=your_latvia_2_password

# Estonia серверы
XUI_HOST_ESTONIA_1=https://estonia-1.chechen-community.online
XUI_LOGIN_ESTONIA_1=your_estonia_1_username
XUI_PASSWORD_ESTONIA_1=your_estonia_1_password

XUI_HOST_ESTONIA_2=https://estonia-2.chechen-community.online
XUI_LOGIN_ESTONIA_2=your_estonia_2_username
XUI_PASSWORD_ESTONIA_2=your_estonia_2_password
```

## Миграция с старой конфигурации

Если у вас уже настроены старые переменные (`XUI_HOST_FINLAND`, `XUI_HOST_LATVIA`, `XUI_HOST_ESTONIA`), просто переименуйте их:

```bash
# Старые переменные -> Новые переменные
XUI_HOST_FINLAND -> XUI_HOST_FINLAND_1
XUI_LOGIN_FINLAND -> XUI_LOGIN_FINLAND_1
XUI_PASSWORD_FINLAND -> XUI_PASSWORD_FINLAND_1

XUI_HOST_LATVIA -> XUI_HOST_LATVIA_1
XUI_LOGIN_LATVIA -> XUI_LOGIN_LATVIA_1
XUI_PASSWORD_LATVIA -> XUI_PASSWORD_LATVIA_1

XUI_HOST_ESTONIA -> XUI_HOST_ESTONIA_1
XUI_LOGIN_ESTONIA -> XUI_LOGIN_ESTONIA_1
XUI_PASSWORD_ESTONIA -> XUI_PASSWORD_ESTONIA_1
```

## Как это работает

1. **Выбор локации**: Пользователь сначала выбирает локацию (Finland, Latvia, Estonia) или "Автовыбор"
2. **Распределение нагрузки**: Бот автоматически выбирает сервер с наименьшим количеством клиентов в выбранной локации
3. **Автовыбор**: При выборе "Автовыбор" бот сравнивает нагрузку всех локаций и выбирает лучшую
4. **Отказоустойчивость**: Если сервер недоступен, бот переключится на другой сервер той же локации
5. **Масштабируемость**: Легко добавить больше серверов в любую локацию

## Добавление больше серверов

Чтобы добавить третий сервер для Finland:

1. Добавьте переменные в `.env`:
```bash
XUI_HOST_FINLAND_3=https://finland-3.chechen-community.online
XUI_LOGIN_FINLAND_3=your_finland_3_username
XUI_PASSWORD_FINLAND_3=your_finland_3_password
```

2. Добавьте сервер в `bot/bot.py`:
```python
{
    "name": "Finland-3", 
    "host": os.getenv("XUI_HOST_FINLAND_3"),
    "login": os.getenv("XUI_LOGIN_FINLAND_3"),
    "password": os.getenv("XUI_PASSWORD_FINLAND_3")
},
```

3. Добавьте переменные в `docker-compose.yml`:
```yaml
- XUI_HOST_FINLAND_3=${XUI_HOST_FINLAND_3}
- XUI_LOGIN_FINLAND_3=${XUI_LOGIN_FINLAND_3}
- XUI_PASSWORD_FINLAND_3=${XUI_PASSWORD_FINLAND_3}
```

## Проверка конфигурации

При запуске бот проверит все серверы и выведет предупреждения для неправильно настроенных серверов:

```
ВНИМАНИЕ: Сервер Finland-2 не настроен! Проверьте переменные XUI_HOST_FINLAND_2, XUI_LOGIN_FINLAND_2, XUI_PASSWORD_FINLAND_2
```

## Рекомендации

1. **Настройте все серверы**: Даже если у вас пока только один сервер на локацию, настройте переменные для второго сервера (можно использовать те же данные)
2. **Мониторинг**: Следите за логами бота для выявления проблем с серверами
3. **Резервное копирование**: Регулярно создавайте резервные копии конфигурации серверов
