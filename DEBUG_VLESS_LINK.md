# Отладка проблемы с VLESS ссылками

## Проблема
Подписка обновляется, но VPN не работает через ссылку.

## Диагностика

### 1. Проверьте, какую ссылку генерирует бот

```bash
# На сервере проверьте логи
sudo docker compose logs -f telegram-bot | grep "VLESS ссылка\|Используется VPN host"
```

### 2. Получите реальную ссылку из subscription endpoint

```bash
# Получите токен подписки из базы данных
sudo sqlite3 /root/Daralla/data/subscribers.db "SELECT subscription_token FROM subscriptions WHERE status='active' LIMIT 1;"

# Проверьте subscription endpoint
curl https://ghosttunnel.space/sub/<token>
```

### 3. Сравните с рабочим конфигом

В вашем рабочем конфиге:
- IP: `192.145.28.122`
- Порт: `443`
- Network: `xhttp`
- Host: `ads.x5.ru`
- Path: `/`
- Mode: `auto`
- Security: `reality`
- PublicKey: `V-5WsdvAka4Q-nzbBA8mbQHEuxDaTdPp43pbrNFAoh8`
- Fingerprint: `chrome`
- SNI: `ads.x5.ru`
- ShortId: `4f`

### 4. Проверьте формат VLESS ссылки

Правильный формат для XHTTP + Reality:
```
vless://{uuid}@{host}:{port}?type=xhttp&encryption=none&path={path}&host={xhttp_host}&mode={mode}&security=reality&pbk={publicKey}&fp={fingerprint}&sni={sni}&sid={shortId}&spx={spx}
```

### 5. Возможные проблемы

#### Проблема 1: Неправильный порядок параметров
Порядок параметров в VLESS ссылке важен!

#### Проблема 2: Неправильные значения параметров
- `path` должен быть закодирован (URL encoded)
- `spx` должен быть закодирован
- `host` в xhttpSettings должен совпадать с SNI

#### Проблема 3: Неправильный IP/порт
- IP должен быть доступен из интернета
- Порт должен быть открыт в firewall

#### Проблема 4: Неправильные Reality настройки
- `publicKey` должен быть правильным
- `shortId` должен совпадать
- `sni` (serverName) должен совпадать с `host` в xhttpSettings

## Решение

### Шаг 1: Проверьте логи генерации ссылки

```bash
sudo docker compose logs telegram-bot | grep -A 5 "VLESS ссылка\|XHTTP параметры\|Reality настройки"
```

### Шаг 2: Сравните сгенерированную ссылку с рабочим конфигом

Декодируйте VLESS ссылку и сравните параметры.

### Шаг 3: Проверьте настройки в X-UI

1. Зайдите в панель X-UI
2. Откройте настройки inbound
3. Проверьте:
   - Network: должен быть `xhttp`
   - XHTTP Settings: host, path, mode
   - Reality Settings: publicKey, fingerprint, serverName, shortIds

### Шаг 4: Проверьте доступность сервера

```bash
# Проверьте пинг
ping 192.145.28.122

# Проверьте порт
telnet 192.145.28.122 443
# или
nc -zv 192.145.28.122 443
```

## Быстрая проверка

Выполните команду и покажите результат:

```bash
# Получите токен подписки
sudo sqlite3 /root/Daralla/data/subscribers.db "SELECT subscription_token FROM subscriptions WHERE status='active' LIMIT 1;"

# Получите ссылки
curl https://ghosttunnel.space/sub/<token>
```

Покажите результат - я смогу сравнить с рабочим конфигом и найти проблему.


