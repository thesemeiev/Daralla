# Функции Subscription Endpoint

## Реализованные функции

### 1. Автоматическое название группы подписки (Remarks)

**Для V2RayTun и других клиентов:**
- Поле `remark` в заголовке `Subscription-UserInfo` (base64 JSON)
- Значение берется из `VPN_BRAND_NAME` в `bot.py`
- Клиенты автоматически отображают это название как "Remarks"

**Для Happ клиента:**
- Заголовок `new-domain` в HTTP ответе
- Комментарий `#new-domain {domain_name}` в теле ответа
- Рекомендуется использовать поддомен в URL подписки (например, `daralla-vpn.ghosttunnel.space`)

**Дополнительные заголовки:**
- `profile-title` - название профиля (Marzban формат)
- `X-Subscription-Name` - альтернативное название (ASCII только)

### 2. Время истечения подписки

**Реализация:**
- Поле `expire` в заголовке `Subscription-UserInfo`
- Значение: Unix timestamp времени истечения подписки
- Клиенты автоматически отображают дату истечения

### 3. Статистика трафика (потребление и остаток)

**Реализация:**
- Поля `upload`, `download`, `total` в заголовке `Subscription-UserInfo`
- Статистика получается из 3x-ui API через метод `get_client_traffic()`
- Для мультисерверных подписок трафик суммируется со всех серверов
- Значения в байтах

**Как работает:**
1. При запросе subscription endpoint получаем список серверов подписки
2. Для каждого сервера получаем статистику трафика клиента из 3x-ui
3. Суммируем `upload` и `download` со всех серверов
4. Берем максимальное значение `total` (если лимиты разные)

**Если статистика недоступна:**
- Используются значения по умолчанию (0, 0, 0)
- Подписка продолжает работать, просто без отображения статистики

### 4. Кнопки на сайт и Telegram

**Реализация:**
- Переменные окружения: `WEBSITE_URL` и `TELEGRAM_URL`
- Добавляются в заголовок `Subscription-UserInfo` (поля `website`, `support-url`, `telegram`, `telegram-url`)
- Добавляются в HTTP заголовки (`support-url`, `telegram-url`)
- Добавляются в комментарии в теле ответа (`#website:`, `#telegram:`)

**Настройка:**
```bash
# В .env файле
WEBSITE_URL=https://daralla-vpn.com
TELEGRAM_URL=https://t.me/daralla_vpn
```

**Поддержка клиентов:**
- Не все клиенты поддерживают кнопки
- Зависит от конкретной реализации клиента
- Некоторые клиенты могут использовать заголовки, другие - комментарии

## Формат Subscription-UserInfo

```json
{
  "upload": 1234567890,      // Upload трафик в байтах
  "download": 9876543210,    // Download трафик в байтах
  "total": 10737418240,      // Общий лимит трафика в байтах (0 = безлимит)
  "expire": 1768620072,      // Unix timestamp времени истечения
  "remark": "🌐 Daralla VPN", // Название группы подписки
  "website": "https://...",  // Ссылка на сайт (опционально)
  "support-url": "https://...", // Ссылка на поддержку (опционально)
  "telegram": "https://...",  // Ссылка на Telegram (опционально)
  "telegram-url": "https://..." // Альтернативная ссылка на Telegram (опционально)
}
```

Заголовок кодируется в base64 и передается как:
```
Subscription-UserInfo: <base64_encoded_json>
```

## HTTP Заголовки

```
Subscription-UserInfo: <base64_json>
Content-Disposition: attachment; filename="daralla-vpn"
new-domain: daralla-vpn
X-Subscription-Name: Daralla VPN
profile-title: Daralla VPN
support-url: https://daralla-vpn.com (если установлен)
telegram-url: https://t.me/daralla_vpn (если установлен)
```

## Комментарии в теле ответа

```
#new-domain daralla-vpn
# name: 🌐 Daralla VPN
#title: 🌐 Daralla VPN
#website: https://daralla-vpn.com (если установлен)
#telegram: https://t.me/daralla_vpn (если установлен)
vless://...
```

## Важные замечания

1. **Официальной документации нет** - реализация основана на:
   - Анализе работы других VPN ботов
   - Информации из Marzban документации
   - Тестировании с различными клиентами

2. **Поддержка клиентов различается:**
   - V2RayTun: поддерживает `remark`, `expire`, `upload`, `download`, `total`
   - Happ: использует домен из URL или заголовок `new-domain`
   - v2rayNG: поддерживает `Subscription-UserInfo`
   - Другие клиенты: могут поддерживать частично или не поддерживать

3. **Рекомендации:**
   - Используйте поддомен для Happ клиента (как `auth.zkodes.ru`)
   - Установите `WEBSITE_URL` и `TELEGRAM_URL` для кнопок
   - Проверяйте работу в разных клиентах

## Настройка

### 1. Название VPN

В `bot.py`:
```python
VPN_BRAND_NAME = "🌐 Daralla VPN"  # Измените на свое название
```

### 2. Ссылки на сайт и Telegram

В `.env` файле:
```bash
WEBSITE_URL=https://your-website.com
TELEGRAM_URL=https://t.me/your_channel
```

### 3. Поддомен для Happ (опционально)

В `.env` файле:
```bash
SUBSCRIPTION_URL=https://daralla-vpn.ghosttunnel.space
```

Если не установлен, используется `WEBHOOK_URL`.

## Тестирование

После настройки проверьте:

1. **V2RayTun:**
   - Название группы должно быть из `remark`
   - Время истечения должно отображаться
   - Статистика трафика должна показываться

2. **Happ:**
   - Название группы должно быть из поддомена или `new-domain`
   - Кнопки могут отображаться (если поддерживаются)

3. **v2rayNG:**
   - Должен поддерживать `Subscription-UserInfo`
   - Статистика и время истечения должны отображаться

