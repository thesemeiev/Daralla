# Исправление ошибки 502 Bad Gateway

## Проблема
Сервер возвращает `502 Bad Gateway` при запросе subscription endpoint.

## Диагностика

### 1. Проверьте, запущен ли Docker контейнер

```bash
# На сервере
cd /path/to/Daralla  # Перейдите в папку с проектом
docker compose ps
```

**Ожидаемый результат:**
```
NAME           IMAGE          STATUS
daralla-bot    daralla-...    Up X minutes
```

**Если контейнер не запущен:**
```bash
docker compose up -d
docker compose logs -f daralla-telegram-bot
```

### 2. Проверьте логи бота

```bash
# Проверьте, запустился ли Flask webhook сервер
docker compose logs daralla-telegram-bot | grep -i "webhook\|5000\|flask"

# Должно быть сообщение:
# "Webhook сервер запущен на порту 5000"
```

**Если сообщения нет:**
- Бот не запустился или упал
- Проверьте логи на ошибки: `docker compose logs daralla-telegram-bot | tail -50`

### 3. Проверьте, что порт 5000 открыт в контейнере

```bash
# Проверьте проброс портов
docker port daralla-bot

# Должно показать:
# 5000/tcp -> 0.0.0.0:5000
```

### 4. Проверьте, что Flask отвечает локально

```bash
# На сервере, внутри контейнера
docker compose exec daralla-telegram-bot curl http://localhost:5000/sub/test

# Или снаружи контейнера
curl http://localhost:5000/sub/test
```

**Если не отвечает:**
- Flask не запустился
- Проверьте логи: `docker compose logs daralla-telegram-bot`

### 5. Проверьте конфигурацию Nginx

```bash
# Проверьте конфигурацию
sudo nginx -t

# Должно быть: "syntax is ok" и "test is successful"
```

**Проверьте файл конфигурации:**
```bash
sudo nano /etc/nginx/sites-available/ghosttunnel.space
```

**Должно быть:**
```nginx
server {
    listen 80;
    listen [::]:80;
    server_name ghosttunnel.space www.ghosttunnel.space;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Таймауты для стабильной работы
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

**Если используется HTTPS:**
```nginx
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ghosttunnel.space www.ghosttunnel.space;

    ssl_certificate /etc/letsencrypt/live/ghosttunnel.space/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ghosttunnel.space/privkey.pem;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Таймауты для стабильной работы
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

### 6. Проверьте логи Nginx

```bash
# Ошибки Nginx
sudo tail -f /var/log/nginx/error.log

# Доступ
sudo tail -f /var/log/nginx/access.log
```

**Типичные ошибки:**
- `connect() failed (111: Connection refused)` - Flask не запущен
- `upstream timed out` - Flask не отвечает
- `no resolver defined` - проблема с DNS

### 7. Перезапустите сервисы

```bash
# Перезапустите Docker контейнер
cd /path/to/Daralla
docker compose restart

# Перезагрузите Nginx
sudo systemctl reload nginx
# или
sudo systemctl restart nginx
```

## Быстрое исправление

Если ничего не помогло, выполните полный перезапуск:

```bash
# 1. Остановите контейнер
cd /path/to/Daralla
docker compose down

# 2. Проверьте .env файл
cat .env | grep WEBHOOK_URL

# 3. Запустите заново
docker compose up -d

# 4. Проверьте логи
docker compose logs -f daralla-telegram-bot

# 5. Дождитесь сообщения "Webhook сервер запущен на порту 5000"

# 6. Проверьте локально
curl http://localhost:5000/sub/test

# 7. Перезагрузите Nginx
sudo systemctl reload nginx

# 8. Проверьте через домен
curl https://ghosttunnel.space/sub/test
```

## Проверка после исправления

```bash
# Проверьте subscription endpoint
curl -v https://ghosttunnel.space/sub/9a9ac3215a3f46739974dd1b

# Должен вернуть VLESS ссылки или ошибку 403/404 (но не 502!)
```

## Если проблема сохраняется

1. **Проверьте firewall:**
   ```bash
   sudo ufw status
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   ```

2. **Проверьте, что порт 5000 не занят другим процессом:**
   ```bash
   sudo netstat -tlnp | grep 5000
   # или
   sudo ss -tlnp | grep 5000
   ```

3. **Проверьте Docker сеть:**
   ```bash
   docker network ls
   docker network inspect daralla_bot-network
   ```

4. **Проверьте переменные окружения:**
   ```bash
   docker compose exec daralla-telegram-bot env | grep WEBHOOK
   ```

