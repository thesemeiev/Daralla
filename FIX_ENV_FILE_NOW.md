# Срочное исправление .env файла

## Проблемы в текущем .env файле:

1. ❌ `NETHERLANDS\# Telegram Bot Configuration` - неправильный формат
2. ❌ Два раза `WEBHOOK_URL` (HTTP и HTTPS)
3. ❌ Нет комментария для Netherlands секции

## Правильный формат .env файла:

Скопируйте и вставьте это в `/root/Daralla/.env`:

```env
# Telegram Bot Configuration
ADMIN_ID=6735703554
TELEGRAM_TOKEN=8404897519:AAF6PQCLrEdBNLAh1ITBIy9TdtmUIZX5gd8

# YooKassa Payment Configuration
YOOKASSA_SHOP_ID=1128790
YOOKASSA_SECRET_KEY=test_DDkUUFRk22GFIpQRP6w6FEgDDZUfyFzYBq_ese42IwE

# Webhook Configuration
WEBHOOK_URL=https://ghosttunnel.space
WEBSITE_URL=https://ghosttunnel.space
TELEGRAM_URL=https://t.me/darlla_bot

# 3x-ui Server Configuration - Latvia
XUI_HOST_LATVIA_1=http://192.145.28.122:44764
XUI_LOGIN_LATVIA_1=thesemeiev
XUI_PASSWORD_LATVIA_1=Abdu-Rahman_2506
XUI_VPN_HOST_LATVIA_1=192.145.28.122

# 3x-ui Server Configuration - Netherlands
XUI_HOST_NETHERLANDS_1=http://192.145.31.253:3687
XUI_LOGIN_NETHERLANDS_1=thesemeiev
XUI_PASSWORD_NETHERLANDS_1=Abdu-Rahman_2506
XUI_VPN_HOST_NETHERLANDS_1=192.145.31.253
```

## Команды для исправления на сервере:

```bash
cd /root/Daralla

# Создайте резервную копию
sudo cp .env .env.backup

# Откройте файл для редактирования
sudo nano .env
```

**Удалите:**
- Строку `NETHERLANDS\# Telegram Bot Configuration`
- Дублирующийся `WEBHOOK_URL=http://ghosttunnel.space`
- Комментарий `# Для HTTP (временно)`
- Комментарий `# Для HTTPS (после настройки SSL)`

**Оставьте только:**
- `WEBHOOK_URL=https://ghosttunnel.space` (один раз)
- Правильные комментарии с `#` (без `\`)

**Или просто замените весь файл содержимым выше.**

После исправления:

```bash
# Проверьте формат файла (убедитесь, что нет Windows окончаний строк)
sudo dos2unix .env

# Перезапустите Docker
sudo docker compose down
sudo docker compose up -d

# Проверьте логи
sudo docker compose logs -f telegram-bot
```

