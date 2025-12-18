# Настройка Webhook'ов для YooKassa (тестовый магазин)

## Проблема
Вебхуки от YooKassa не приходят, платежи не подтверждаются автоматически.

## Решение

### 1. Получите публичный URL для вебхука

Вебхук должен быть доступен из интернета. Есть два варианта:

#### Вариант A: Использовать домен (рекомендуется)

Если у вас есть домен `ghosttunnel.space`:

1. **Настройте Nginx** (если еще не настроен):
   ```bash
   # На сервере
   sudo nano /etc/nginx/sites-available/ghosttunnel.space
   ```

   Добавьте конфигурацию:
   ```nginx
   server {
       listen 80;
       server_name ghosttunnel.space www.ghosttunnel.space;

       location / {
           proxy_pass http://localhost:5000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

2. **Настройте SSL** (обязательно для YooKassa):
   ```bash
   sudo apt-get install certbot python3-certbot-nginx
   sudo certbot --nginx -d ghosttunnel.space -d www.ghosttunnel.space
   ```

3. **Обновите .env файл**:
   ```bash
   WEBHOOK_URL=https://ghosttunnel.space
   ```

#### Вариант B: Использовать ngrok (для тестирования)

1. **Получите ngrok Auth Token:**
   - Зайдите на [https://ngrok.com/signup](https://ngrok.com/signup)
   - Зарегистрируйтесь (бесплатно)
   - Войдите в [Dashboard](https://dashboard.ngrok.com/get-started/your-authtoken)
   - Скопируйте ваш **Auth Token**

2. **Добавьте токен в .env файл:**
   ```bash
   NGROK_AUTH_TOKEN=ваш_токен_здесь
   ```

3. **Запустите ngrok** (если не настроен автоматически):
   ```bash
   ngrok http 5000 --authtoken $NGROK_AUTH_TOKEN
   ```

4. **Получите ngrok URL** и добавьте в .env:
   ```bash
   WEBHOOK_URL=https://xxxx-xx-xx-xx-xx.ngrok.io
   ```

### 2. Настройте Webhook в личном кабинете YooKassa

**Важно:** Для тестового магазина нужно настроить отдельно!

1. **Зайдите в личный кабинет YooKassa:**
   - Тестовый магазин: [https://yookassa.ru/my](https://yookassa.ru/my)
   - Или переключитесь на тестовый режим в настройках

2. **Перейдите в настройки Webhook:**
   - **Настройки** → **Webhook** (или **Уведомления**)
   - Или прямой URL: `https://yookassa.ru/my/webhooks`

3. **Добавьте новый Webhook:**
   - Нажмите **"Добавить webhook"** или **"Создать"**
   - **URL:** `https://ghosttunnel.space/webhook/yookassa`
     - Или если используете ngrok: `https://xxxx.ngrok.io/webhook/yookassa`
   - **События:** Выберите:
     - ✅ `payment.succeeded` (обязательно!)
     - ✅ `payment.canceled` (опционально)
     - ✅ `payment.refunded` (опционально)

4. **Сохраните настройки**

### 3. Проверьте .env файл на сервере

```bash
# На тестовом сервере
cd /root/Daralla
cat .env | grep WEBHOOK_URL
```

Должно быть:
```env
WEBHOOK_URL=https://ghosttunnel.space
# или
WEBHOOK_URL=https://xxxx.ngrok.io
```

**Важно:**
- URL должен начинаться с `https://` (не `http://`)
- URL должен быть доступен из интернета
- Не должно быть слеша в конце: `https://domain.com` (не `https://domain.com/`)

### 4. Перезапустите бота

```bash
cd /root/Daralla
sudo docker compose down
sudo docker compose up -d
sudo docker compose logs -f telegram-bot
```

### 5. Проверьте работу вебхука

#### Тест 1: Проверка доступности эндпоинта

```bash
# С сервера
curl -X POST http://localhost:5000/webhook/yookassa \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'
```

Должен вернуть JSON ответ (даже если ошибка).

#### Тест 2: Проверка через публичный URL

```bash
# С любого компьютера
curl -X POST https://ghosttunnel.space/webhook/yookassa \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'
```

#### Тест 3: Создайте тестовый платеж

1. Создайте платеж через бота
2. Оплатите его в тестовом режиме YooKassa
3. Проверьте логи бота:
   ```bash
   sudo docker compose logs -f telegram-bot | grep WEBHOOK
   ```

Должны появиться строки:
```
🔔 WEBHOOK: Получен webhook от YooKassa
🔔 WEBHOOK: Обработка webhook: payment_id=..., status=succeeded
```

### 6. Проверка в личном кабинете YooKassa

1. Зайдите в **Настройки** → **Webhook**
2. Проверьте статус вебхука:
   - ✅ **Активен** - все хорошо
   - ❌ **Неактивен** или **Ошибка** - проверьте URL и доступность

3. Посмотрите **Историю доставок**:
   - Должны быть записи о попытках доставки
   - Если есть ошибки, проверьте логи

## Частые проблемы

### Проблема 1: "Webhook не доставляется"

**Причины:**
- URL недоступен из интернета
- Используется `http://` вместо `https://`
- Порт 5000 не открыт в firewall

**Решение:**
```bash
# Проверьте доступность
curl https://ghosttunnel.space/webhook/yookassa

# Проверьте firewall
sudo ufw status
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

### Проблема 2: "SSL/TLS ошибка"

**Причина:** YooKassa требует HTTPS

**Решение:**
- Настройте SSL сертификат через Let's Encrypt (certbot)
- Или используйте ngrok (автоматически дает HTTPS)

### Проблема 3: "404 Not Found"

**Причина:** Неправильный URL или Nginx не настроен

**Решение:**
```bash
# Проверьте Nginx конфигурацию
sudo nginx -t
sudo systemctl reload nginx

# Проверьте, что Flask доступен локально
curl http://localhost:5000/webhook/yookassa
```

### Проблема 4: "Webhook настроен, но не приходит"

**Причины:**
- Неправильный URL в настройках YooKassa
- Тестовый магазин использует другой webhook URL
- Webhook настроен для продакшн магазина, а вы тестируете в тестовом

**Решение:**
- Убедитесь, что настраиваете webhook для **тестового магазина**
- Проверьте, что используете правильные `YOOKASSA_SHOP_ID` и `YOOKASSA_SECRET_KEY` для тестового магазина

## Для тестового магазина YooKassa

**Важно:** Тестовый и продакшн магазины имеют разные настройки!

1. **Тестовый магазин:**
   - Shop ID начинается с `test_` или имеет специальный формат
   - Secret Key для тестового магазина
   - Webhook настраивается отдельно

2. **Проверьте, что используете тестовые данные:**
   ```bash
   # В .env файле должны быть тестовые данные
   YOOKASSA_SHOP_ID=test_xxxxx  # или другой формат для теста
   YOOKASSA_SECRET_KEY=test_xxxxx  # тестовый ключ
   ```

## Автоматическая настройка через скрипт

Если используете ngrok, можно автоматизировать:

```bash
# На сервере создайте скрипт
cat > /root/setup_webhook.sh << 'EOF'
#!/bin/bash
# Получаем ngrok URL
NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | jq -r '.tunnels[0].public_url')
WEBHOOK_URL="${NGROK_URL}/webhook/yookassa"

echo "Webhook URL: $WEBHOOK_URL"
echo "Настройте этот URL в личном кабинете YooKassa"
EOF

chmod +x /root/setup_webhook.sh
```

## Проверка после настройки

1. ✅ Webhook URL доступен из интернета
2. ✅ Webhook настроен в личном кабинете YooKassa
3. ✅ Используется HTTPS
4. ✅ .env файл содержит правильный WEBHOOK_URL
5. ✅ Бот перезапущен
6. ✅ Создан тестовый платеж и проверены логи

## Дополнительная информация

- **Документация YooKassa:** [https://yookassa.ru/developers/api#webhook](https://yookassa.ru/developers/api#webhook)
- **Тестовые платежи:** Используйте тестовые карты из документации YooKassa
- **Логи вебхуков:** Все вебхуки логируются в `bot/handlers/webhooks/webhook_app.py`

