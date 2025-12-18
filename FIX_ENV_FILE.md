# Исправление проблемы с .env файлом

## Проблема
Бот не может найти переменные окружения `TELEGRAM_TOKEN` и другие.

## Решение

### 1. Проверьте наличие .env файла на сервере

```bash
cd /root/Daralla
ls -la .env
```

Если файл не существует или пустой, создайте его.

### 2. Создайте/отредактируйте .env файл

```bash
cd /root/Daralla
sudo nano .env
```

### 3. Добавьте все необходимые переменные

```env
# Telegram Bot Configuration
TELEGRAM_TOKEN=ваш_токен_бота
ADMIN_ID=ваш_telegram_id

# YooKassa Payment Configuration
YOOKASSA_SHOP_ID=ваш_shop_id
YOOKASSA_SECRET_KEY=ваш_secret_key

# Webhook Configuration
NGROK_AUTH_TOKEN=ваш_ngrok_token_или_пусто
WEBHOOK_URL=https://ghosttunnel.space

# X-UI Server Configuration
XUI_HOST_LATVIA_1=http://185.113.139.11:8172
XUI_LOGIN_LATVIA_1=ваш_логин
XUI_PASSWORD_LATVIA_1=ваш_пароль
```

**Важно:**
- Не используйте кавычки вокруг значений
- Не оставляйте пробелы вокруг знака `=`
- Каждая переменная на новой строке

### 4. Проверьте права доступа

```bash
sudo chmod 644 .env
sudo chown root:root .env
```

### 5. Проверьте содержимое файла

```bash
cat .env
```

Убедитесь, что все переменные заполнены и нет пустых значений.

### 6. Перезапустите контейнер

```bash
sudo docker compose down
sudo docker compose up -d
```

### 7. Проверьте логи

```bash
sudo docker compose logs -f telegram-bot
```

Если ошибка все еще есть, проверьте:

```bash
# Проверьте, что файл монтируется в контейнер
sudo docker compose exec telegram-bot ls -la /app/.env

# Проверьте переменные окружения внутри контейнера
sudo docker compose exec telegram-bot env | grep TELEGRAM_TOKEN
```

## Альтернативное решение: передача переменных напрямую

Если файл `.env` не работает, можно передать переменные напрямую в `docker-compose.yml`:

```yaml
environment:
  - TELEGRAM_TOKEN=ваш_токен
  - ADMIN_ID=ваш_id
  # и т.д.
```

Но лучше использовать `.env` файл, так как он не попадет в git.

## Проверка на тестовом сервере

Если вы настраиваете тестовый сервер, убедитесь, что:

1. Файл `.env` существует в `/root/Daralla/.env`
2. Все переменные заполнены (можно использовать `TEST_` префикс для тестовых значений)
3. Docker Compose может прочитать файл (права доступа)

