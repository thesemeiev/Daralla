# Добавление нескольких серверов

## Пошаговая инструкция

### Шаг 1: Добавьте переменные в .env файл

```bash
cd /root/Daralla
sudo nano .env
```

Добавьте для каждого сервера:

```env
# Latvia сервер 1
XUI_HOST_LATVIA_1=http://185.113.139.11:8172
XUI_LOGIN_LATVIA_1=admin
XUI_PASSWORD_LATVIA_1=password
XUI_VPN_HOST_LATVIA_1=192.145.28.122

# Latvia сервер 2 (если есть)
XUI_HOST_LATVIA_2=http://192.168.1.101:54321
XUI_LOGIN_LATVIA_2=admin
XUI_PASSWORD_LATVIA_2=password
XUI_VPN_HOST_LATVIA_2=192.168.1.101

# Finland сервер 1
XUI_HOST_FINLAND_1=http://192.168.1.200:54321
XUI_LOGIN_FINLAND_1=admin
XUI_PASSWORD_FINLAND_1=password
XUI_VPN_HOST_FINLAND_1=192.168.1.200

# Estonia сервер 1
XUI_HOST_ESTONIA_1=http://192.168.1.300:54321
XUI_LOGIN_ESTONIA_1=admin
XUI_PASSWORD_ESTONIA_1=password
XUI_VPN_HOST_ESTONIA_1=192.168.1.300
```

### Шаг 2: Обновите bot.py

Откройте файл `bot/bot.py` и найдите секцию `SERVERS_BY_LOCATION`:

```python
SERVERS_BY_LOCATION = {
    "Latvia": [
        {
            "name": "Latvia-1",
            "host": os.getenv("XUI_HOST_LATVIA_1"),
            "login": os.getenv("XUI_LOGIN_LATVIA_1"),
            "password": os.getenv("XUI_PASSWORD_LATVIA_1"),
            "vpn_host": os.getenv("XUI_VPN_HOST_LATVIA_1")
        },
        # Добавьте второй сервер Latvia, если есть
        {
            "name": "Latvia-2",
            "host": os.getenv("XUI_HOST_LATVIA_2"),
            "login": os.getenv("XUI_LOGIN_LATVIA_2"),
            "password": os.getenv("XUI_PASSWORD_LATVIA_2"),
            "vpn_host": os.getenv("XUI_VPN_HOST_LATVIA_2")
        },
    ],
    "Finland": [
        {
            "name": "Finland-1",
            "host": os.getenv("XUI_HOST_FINLAND_1"),
            "login": os.getenv("XUI_LOGIN_FINLAND_1"),
            "password": os.getenv("XUI_PASSWORD_FINLAND_1"),
            "vpn_host": os.getenv("XUI_VPN_HOST_FINLAND_1")
        },
    ],
    "Estonia": [
        {
            "name": "Estonia-1",
            "host": os.getenv("XUI_HOST_ESTONIA_1"),
            "login": os.getenv("XUI_LOGIN_ESTONIA_1"),
            "password": os.getenv("XUI_PASSWORD_ESTONIA_1"),
            "vpn_host": os.getenv("XUI_VPN_HOST_ESTONIA_1")
        },
    ],
}
```

### Шаг 3: Обновите docker-compose.yml (если нужно)

Добавьте переменные окружения для новых серверов:

```yaml
environment:
  # ... существующие переменные ...
  
  # Latvia серверы
  - XUI_HOST_LATVIA_1=${XUI_HOST_LATVIA_1}
  - XUI_LOGIN_LATVIA_1=${XUI_LOGIN_LATVIA_1}
  - XUI_PASSWORD_LATVIA_1=${XUI_PASSWORD_LATVIA_1}
  
  # Finland серверы
  - XUI_HOST_FINLAND_1=${XUI_HOST_FINLAND_1}
  - XUI_LOGIN_FINLAND_1=${XUI_LOGIN_FINLAND_1}
  - XUI_PASSWORD_FINLAND_1=${XUI_PASSWORD_FINLAND_1}
  
  # Estonia серверы
  - XUI_HOST_ESTONIA_1=${XUI_HOST_ESTONIA_1}
  - XUI_LOGIN_ESTONIA_1=${XUI_LOGIN_ESTONIA_1}
  - XUI_PASSWORD_ESTONIA_1=${XUI_PASSWORD_ESTONIA_1}
```

**Примечание:** Docker Compose автоматически читает переменные из `.env` файла, так что этот шаг опционален.

### Шаг 4: Перезапустите бота

```bash
cd /root/Daralla
sudo docker compose down
sudo docker compose up -d
```

### Шаг 5: Проверьте логи

```bash
sudo docker compose logs -f telegram-bot | grep "Сервер.*добавлен"
```

Должны появиться сообщения для всех серверов:
```
Сервер Latvia-1 (Latvia) добавлен
Сервер Finland-1 (Finland) добавлен
Сервер Estonia-1 (Estonia) добавлен
```

### Шаг 6: Протестируйте

1. Создайте тестовый платеж
2. Проверьте, что клиент создается на всех серверах
3. Проверьте subscription endpoint:
   ```bash
   curl https://ghosttunnel.space/sub/<token>
   ```
4. Должны вернуться VLESS ссылки для всех серверов

## Важные моменты:

### VPN Host для каждого сервера:

- **Если VPN сервер на том же IP, что и панель** - можно не указывать `XUI_VPN_HOST_*`, будет использоваться IP панели
- **Если VPN сервер на другом IP** - обязательно укажите `XUI_VPN_HOST_*`

### Разные протоколы:

Каждый сервер может иметь свой протокол в X-UI:
- XHTTP (xhttp)
- TCP (tcp)
- WebSocket (ws)
- gRPC (grpc)
- и т.д.

Бот автоматически читает протокол из настроек X-UI для каждого сервера.

### Именование серверов:

Используйте формат: `LOCATION-NUMBER`
- `Latvia-1`, `Latvia-2`
- `Finland-1`, `Finland-2`
- `Estonia-1`, `Estonia-2`

## Пример полной конфигурации:

### .env файл:
```env
# Latvia серверы
XUI_HOST_LATVIA_1=http://185.113.139.11:8172
XUI_LOGIN_LATVIA_1=admin
XUI_PASSWORD_LATVIA_1=password
XUI_VPN_HOST_LATVIA_1=192.145.28.122

# Finland серверы
XUI_HOST_FINLAND_1=http://192.168.1.200:54321
XUI_LOGIN_FINLAND_1=admin
XUI_PASSWORD_FINLAND_1=password
XUI_VPN_HOST_FINLAND_1=192.168.1.200
```

### bot.py:
```python
SERVERS_BY_LOCATION = {
    "Latvia": [
        {
            "name": "Latvia-1",
            "host": os.getenv("XUI_HOST_LATVIA_1"),
            "login": os.getenv("XUI_LOGIN_LATVIA_1"),
            "password": os.getenv("XUI_PASSWORD_LATVIA_1"),
            "vpn_host": os.getenv("XUI_VPN_HOST_LATVIA_1")
        },
    ],
    "Finland": [
        {
            "name": "Finland-1",
            "host": os.getenv("XUI_HOST_FINLAND_1"),
            "login": os.getenv("XUI_LOGIN_FINLAND_1"),
            "password": os.getenv("XUI_PASSWORD_FINLAND_1"),
            "vpn_host": os.getenv("XUI_VPN_HOST_FINLAND_1")
        },
    ],
}
```

## Проверка после добавления:

```bash
# Проверьте, что все серверы видны
sudo docker compose logs telegram-bot | grep "Сервер.*добавлен"

# Проверьте статус серверов через бота
# Используйте команду /admin_check_servers в Telegram
```

## Готово!

После добавления серверов:
- ✅ При покупке подписки клиент создается на всех серверах
- ✅ Каждый сервер генерирует свою VLESS ссылку с правильным протоколом
- ✅ Subscription endpoint возвращает все ссылки
- ✅ Каждый сервер использует свой VPN host

