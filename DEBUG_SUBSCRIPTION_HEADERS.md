# Отладка заголовков подписки для Happ и V2RayTun

## Проблема

В Happ показывается только кнопка на сайт (но не на Telegram), в V2RayTun нет даже кнопки на сайт.

## Что было добавлено

### 1. Множественные форматы заголовков

Добавлены различные варианты заголовков для максимальной совместимости:

**Для сайта (website_url):**
- `support-url` (lowercase с дефисом)
- `support_url` (с подчеркиванием)
- `supportUrl` (camelCase)
- `Support-Url` (CamelCase с дефисом)
- `SupportUrl` (CamelCase без дефиса)
- `SupportURL` (все заглавные)
- `website` (простое название)
- `Website` (с заглавной буквы)
- `X-Support-URL` (с префиксом X-)
- `X-Website-URL` (с префиксом X-)

**Для Telegram (telegram_url):**
- `telegram-url` (lowercase с дефисом)
- `telegram_url` (с подчеркиванием)
- `telegramUrl` (camelCase)
- `Telegram-Url` (CamelCase с дефисом)
- `TelegramUrl` (CamelCase без дефиса)
- `TelegramURL` (все заглавные)
- `telegram` (простое название)
- `Telegram` (с заглавной буквы)
- `tg` (короткое название)
- `TG` (короткое заглавное)
- `tg-url` (с дефисом)
- `X-Telegram-URL` (с префиксом X-)
- `X-TG-URL` (с префиксом X-)

### 2. Множественные форматы в Subscription-UserInfo

В JSON объекте `Subscription-UserInfo` добавлены поля:
- `website`, `support-url`, `supportUrl`, `support_url`, `support`
- `telegram`, `telegram-url`, `telegramUrl`, `telegram_url`, `tg`, `tg-url`

### 3. Комментарии в теле ответа

Добавлены комментарии:
- `#website:`, `#support-url:`
- `#telegram:`, `#telegram-url:`, `#tg:`

## Как проверить заголовки

### 1. Проверка через curl

```bash
curl -I "https://ghosttunnel.space/sub/YOUR_TOKEN"
```

Или с полным выводом заголовков:

```bash
curl -v "https://ghosttunnel.space/sub/YOUR_TOKEN" 2>&1 | grep -i "support\|telegram\|website"
```

### 2. Проверка через браузер (DevTools)

1. Откройте DevTools (F12)
2. Перейдите на вкладку Network
3. Откройте URL подписки в браузере
4. Найдите запрос и проверьте заголовки ответа (Response Headers)

### 3. Проверка Subscription-UserInfo

```bash
# Получить заголовок Subscription-UserInfo
curl -s "https://ghosttunnel.space/sub/YOUR_TOKEN" -I | grep "Subscription-UserInfo"

# Декодировать base64
echo "BASE64_VALUE" | base64 -d | jq .
```

Или через Python:

```python
import base64
import json

# Замените на реальное значение из заголовка
base64_value = "eyJ1cGxvYWQiOjAsImRvd25sb2FkIjowLCJ0b3RhbCI6MCwiZXhwaXJlIjoxNzY4NjIwMDcyLCJleHBpcnlUaW1lIjoxNzY4NjIwMDcyMDAwLCJyZW1hcmsiOiLwn4yIIERhcmFsbGEgVlBOIn0="

json_str = base64.b64decode(base64_value).decode('utf-8')
data = json.loads(json_str)
print(json.dumps(data, indent=2, ensure_ascii=False))
```

## Проверка логов

В логах бота теперь выводится:
- `Subscription-UserInfo JSON: {...}` - полный JSON объект
- `Subscription-UserInfo Base64: ...` - первые 100 символов base64

Проверьте логи:

```bash
sudo docker compose logs telegram-bot | grep "Subscription-UserInfo"
```

## Возможные причины проблемы

### 1. Клиенты не поддерживают кнопки

**Happ** и **V2RayTun** могут не поддерживать отображение кнопок через заголовки. Это ограничение самих клиентов, а не сервера.

### 2. Неправильный формат

Возможно, клиенты ожидают другой формат данных. Попробуйте:
- Проверить версию клиента (обновить до последней)
- Проверить документацию клиента
- Связаться с разработчиками клиента

### 3. Кэширование

Клиент может кэшировать старую версию подписки. Попробуйте:
- Удалить подписку и добавить заново
- Очистить кэш приложения
- Перезапустить клиент

## Альтернативные решения

### 1. Информация в комментариях

Некоторые клиенты могут читать информацию из комментариев в теле ответа. Уже добавлены:
- `#website: https://...`
- `#telegram: https://...`

### 2. Информация в названии подписки

Можно добавить ссылки в название подписки (но это не очень удобно):
- `🌐 Daralla VPN | Website: https://... | Telegram: https://...`

### 3. Отдельная инструкция для пользователей

Создать инструкцию, где пользователи могут найти ссылки на сайт и Telegram в боте или на сайте.

## Что проверить дальше

1. **Проверьте логи** - убедитесь, что заголовки отправляются правильно
2. **Проверьте версию клиентов** - обновите Happ и V2RayTun до последних версий
3. **Проверьте документацию клиентов** - возможно, есть специальные требования
4. **Свяжитесь с разработчиками** - спросите, какие заголовки они поддерживают

## Дополнительная информация

Если вы найдете правильный формат для Happ или V2RayTun, сообщите, и мы добавим его в код.

