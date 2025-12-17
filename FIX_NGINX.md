# Исправление проблемы с nginx (404 Not Found)

## Проблема
HTTP запрос возвращает `404 Not Found` от nginx. Это означает, что nginx не проксирует запросы к Flask приложению.

## Решение

### 1. Проверьте конфигурацию nginx на сервере:

```bash
sudo nano /etc/nginx/sites-available/ghosttunnel.space
```

Убедитесь, что конфигурация содержит:

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
        
        # Таймауты
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

### 2. Проверьте, что бот запущен и слушает порт 5000:

```bash
# Проверьте статус контейнера
docker-compose ps

# Проверьте логи
docker-compose logs telegram-bot | grep "Webhook сервер"

# Должно быть: "Webhook сервер запущен на порту 5000"
```

### 3. Проверьте, что порт 5000 доступен локально:

```bash
# На сервере выполните:
curl http://localhost:5000/sub/1b97286f426a4d0687fdc3c3

# Если работает - значит проблема в nginx
# Если не работает - проблема в Flask приложении
```

### 4. Проверьте конфигурацию nginx:

```bash
sudo nginx -t
```

Если есть ошибки - исправьте их.

### 5. Перезагрузите nginx:

```bash
sudo systemctl reload nginx
# или
sudo systemctl restart nginx
```

### 6. Проверьте логи nginx:

```bash
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log
```

### 7. Проверьте, что конфигурация активна:

```bash
# Проверьте симлинк
ls -la /etc/nginx/sites-enabled/ | grep ghosttunnel

# Если нет - создайте:
sudo ln -s /etc/nginx/sites-available/ghosttunnel.space /etc/nginx/sites-enabled/
```

## Проверка после исправления

После исправления nginx, проверьте:

```powershell
# В PowerShell используйте:
Invoke-WebRequest -Uri "http://ghosttunnel.space/sub/1b97286f426a4d0687fdc3c3" -UseBasicParsing

# Или через curl.exe (если установлен):
curl.exe -v http://ghosttunnel.space/sub/1b97286f426a4d0687fdc3c3
```

## Если все еще не работает

1. Проверьте firewall:
```bash
sudo ufw status
# Убедитесь, что порты 80 и 443 открыты
```

2. Проверьте, что Docker контейнер доступен:
```bash
# Проверьте сеть Docker
docker network inspect daralla_bot-network

# Проверьте, что порт проброшен
docker port daralla-bot
```

3. Проверьте, что Flask приложение запущено:
```bash
docker-compose logs telegram-bot | grep -i "webhook\|flask\|5000"
```

