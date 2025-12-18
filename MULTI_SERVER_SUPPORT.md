# Поддержка нескольких серверов с разными протоколами

## ✅ Система уже поддерживает несколько серверов!

Текущая реализация:
- ✅ Создает клиента на всех доступных серверах при покупке
- ✅ Генерирует отдельную VLESS ссылку для каждого сервера
- ✅ Каждый сервер может иметь свой протокол, порт, Reality настройки
- ✅ Поддержка разных VPN хостов для каждого сервера

## Как это работает:

### 1. При покупке подписки:

Система автоматически:
- Создает клиента на **всех доступных серверах**
- Привязывает каждый сервер к подписке
- Каждый сервер сохраняется в `subscription_servers` с уникальным `client_email`

### 2. При генерации VLESS ссылок:

Система:
- Итерируется по **всем серверам** подписки
- Для каждого сервера вызывает `xui.link(client_email)`
- Метод `link()` читает настройки **из X-UI API** каждого сервера:
  - Протокол (network: xhttp, tcp, ws и т.д.)
  - Порт
  - Reality настройки (publicKey, fingerprint, sni, shortId)
  - XHTTP настройки (path, host, mode)
- Использует правильный VPN host для каждого сервера

### 3. Результат:

Возвращается список VLESS ссылок - по одной для каждого сервера:
```
vless://uuid1@server1_ip:port?type=xhttp&... # Сервер 1
vless://uuid2@server2_ip:port?type=tcp&...   # Сервер 2
vless://uuid3@server3_ip:port?type=ws&...    # Сервер 3
```

## Настройка для нескольких серверов:

### Пример .env файла:

```env
# Latvia серверы
XUI_HOST_LATVIA_1=http://185.113.139.11:8172
XUI_LOGIN_LATVIA_1=admin
XUI_PASSWORD_LATVIA_1=password
XUI_VPN_HOST_LATVIA_1=192.145.28.122

# Finland серверы
XUI_HOST_FINLAND_1=http://192.168.1.100:54321
XUI_LOGIN_FINLAND_1=admin
XUI_PASSWORD_FINLAND_1=password
XUI_VPN_HOST_FINLAND_1=192.168.1.100

# Estonia серверы
XUI_HOST_ESTONIA_1=http://10.0.0.50:54321
XUI_LOGIN_ESTONIA_1=admin
XUI_PASSWORD_ESTONIA_1=password
XUI_VPN_HOST_ESTONIA_1=10.0.0.50
```

### Обновление bot.py:

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

## Как работает генерация ссылок для разных протоколов:

### Метод `link()` автоматически определяет:

1. **Протокол** из `stream.network`:
   - `xhttp` - XHTTP протокол
   - `tcp` - TCP протокол
   - `ws` - WebSocket
   - `grpc` - gRPC
   - и т.д.

2. **Порт** из `inbounds.port`

3. **Reality настройки** из `stream.realitySettings`:
   - `publicKey` (pbk)
   - `fingerprint` (fp)
   - `serverName` (sni)
   - `shortIds` (sid)
   - `spiderX` (spx)

4. **XHTTP настройки** из `stream.xhttpSettings`:
   - `path`
   - `host`
   - `mode`

5. **VPN Host** из конфигурации (`vpn_host` или `host`)

## Пример работы:

### Сервер 1 (XHTTP + Reality):
```
vless://uuid@192.145.28.122:443?type=xhttp&encryption=none&path=%2F&host=ads.x5.ru&mode=auto&security=reality&pbk=...&fp=chrome&sni=ads.x5.ru&sid=4f&spx=%2F
```

### Сервер 2 (TCP + Reality):
```
vless://uuid@192.168.1.100:443?type=tcp&security=reality&pbk=...&fp=chrome&sni=google.com&sid=abc&spx=%2F
```

### Сервер 3 (WebSocket):
```
vless://uuid@10.0.0.50:443?type=ws&path=%2Fpath&security=reality&pbk=...&fp=chrome&sni=example.com&sid=xyz&spx=%2F
```

## Важно:

1. **Каждый сервер настраивается в X-UI** со своими протоколами и настройками
2. **Бот автоматически читает** настройки из X-UI API для каждого сервера
3. **VPN host указывается отдельно** для каждого сервера (если отличается от панели)
4. **Все ссылки возвращаются** в subscription endpoint (`/sub/<token>`)

## Проверка:

После настройки нескольких серверов:

1. Создайте тестовую подписку
2. Проверьте логи:
   ```bash
   sudo docker compose logs -f telegram-bot | grep "VLESS ссылка"
   ```
3. Должны быть ссылки для всех серверов
4. Проверьте subscription endpoint:
   ```bash
   curl https://ghosttunnel.space/sub/<token>
   ```
5. Должны вернуться все VLESS ссылки (по одной на строку)

## Масштабирование:

Система автоматически поддерживает:
- ✅ Любое количество серверов
- ✅ Разные протоколы на каждом сервере
- ✅ Разные порты
- ✅ Разные Reality настройки
- ✅ Разные VPN хосты

Просто добавьте серверы в `SERVERS_BY_LOCATION` и соответствующие переменные в `.env`!

