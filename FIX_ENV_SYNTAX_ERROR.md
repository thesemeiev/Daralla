# Исправление ошибки синтаксиса .env файла

## Проблема
```
failed to read /root/Daralla/.env: line 1: unexpected character "\\" in variable name "NETHERLANDS\\# Telegram Bot Configuration\r"
```

## Причина
В `.env` файле есть строка с символом `\` перед `#`, что делает `#` частью имени переменной вместо комментария.

## Решение

### 1. Откройте .env файл на сервере

```bash
cd /root/Daralla
sudo nano .env
```

### 2. Найдите и исправьте проблемные строки

**Неправильно:**
```env
NETHERLANDS\# Telegram Bot Configuration
XUI_HOST_NETHERLANDS_1=...
```

**Правильно:**
```env
# Netherlands серверы
XUI_HOST_NETHERLANDS_1=...
```

### 3. Правильный формат .env файла

```env
# Telegram Bot Configuration
TELEGRAM_TOKEN=ваш_токен
ADMIN_ID=ваш_id

# YooKassa Payment Configuration
YOOKASSA_SHOP_ID=ваш_shop_id
YOOKASSA_SECRET_KEY=ваш_secret_key

# Webhook Configuration
WEBHOOK_URL=https://ghosttunnel.space
WEBSITE_URL=https://your-website.com
TELEGRAM_URL=https://t.me/your_channel

# 3x-ui Server Configuration - Latvia
XUI_HOST_LATVIA_1=http://185.113.139.11:8172
XUI_LOGIN_LATVIA_1=ваш_логин
XUI_PASSWORD_LATVIA_1=ваш_пароль
XUI_VPN_HOST_LATVIA_1=192.145.28.122

# 3x-ui Server Configuration - Netherlands
XUI_HOST_NETHERLANDS_1=http://ip:port
XUI_LOGIN_NETHERLANDS_1=ваш_логин
XUI_PASSWORD_NETHERLANDS_1=ваш_пароль
XUI_VPN_HOST_NETHERLANDS_1=ip_адрес
```

### 4. Важные правила для .env файла

- ✅ Используйте `#` для комментариев (БЕЗ `\` перед ним)
- ✅ Каждая переменная на новой строке
- ✅ Формат: `VARIABLE_NAME=value` (без пробелов вокруг `=`)
- ✅ Не используйте кавычки вокруг значений
- ✅ Не используйте `\` в комментариях
- ✅ Используйте Unix формат окончаний строк (LF, не CRLF)

### 5. Проверьте формат файла

```bash
# Проверьте, нет ли Windows окончаний строк (CRLF)
file .env

# Если показывает "CRLF", конвертируйте в Unix формат:
sudo dos2unix .env
# или
sudo sed -i 's/\r$//' .env
```

### 6. Проверьте синтаксис

```bash
# Проверьте, что файл читается правильно
cat .env

# Убедитесь, что нет символов `\` перед `#`
grep -n "\\\\#" .env
# Если находит строки - исправьте их
```

### 7. Перезапустите Docker

```bash
cd /root/Daralla
sudo docker compose down
sudo docker compose up -d
```

### 8. Проверьте логи

```bash
sudo docker compose logs -f telegram-bot
```

## Быстрое исправление

Если файл сильно поврежден, создайте новый:

```bash
cd /root/Daralla

# Создайте резервную копию
sudo cp .env .env.backup

# Создайте новый .env файл
sudo nano .env
```

Вставьте правильный формат (см. выше) и сохраните.

