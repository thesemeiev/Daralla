# Исправление ошибки SSL сертификата

## Проблема
```
SSL: no alternative certificate subject name matches target host name 'ghosttunnel.space'
```

Это означает, что SSL сертификат не настроен или настроен неправильно для домена `ghosttunnel.space`.

## Решение

### Шаг 1: Проверьте текущую конфигурацию Nginx

```bash
# Проверьте конфигурацию Nginx
sudo nginx -t

# Посмотрите текущую конфигурацию
sudo cat /etc/nginx/sites-available/ghosttunnel.space
sudo cat /etc/nginx/sites-enabled/ghosttunnel.space
```

### Шаг 2: Проверьте, установлен ли SSL сертификат

```bash
# Проверьте наличие сертификата
sudo ls -la /etc/letsencrypt/live/ghosttunnel.space/

# Или проверьте все сертификаты
sudo certbot certificates
```

### Шаг 3: Установите/обновите SSL сертификат

#### Вариант A: Если сертификат не установлен

```bash
# Установите certbot (если не установлен)
sudo apt-get update
sudo apt-get install -y certbot python3-certbot-nginx

# Получите сертификат для домена
sudo certbot --nginx -d ghosttunnel.space -d www.ghosttunnel.space

# Следуйте инструкциям:
# - Введите email
# - Согласитесь с условиями
# - Выберите редирект HTTP на HTTPS (рекомендуется)
```

#### Вариант B: Если сертификат установлен, но не работает

```bash
# Обновите сертификат
sudo certbot renew

# Перезагрузите Nginx
sudo systemctl reload nginx
```

### Шаг 4: Проверьте конфигурацию Nginx

После установки certbot автоматически обновит конфигурацию. Проверьте:

```bash
sudo cat /etc/nginx/sites-available/ghosttunnel.space
```

Должно быть что-то вроде:

```nginx
server {
    listen 80;
    server_name ghosttunnel.space www.ghosttunnel.space;
    
    # Редирект на HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name ghosttunnel.space www.ghosttunnel.space;

    # SSL сертификаты (добавлены certbot)
    ssl_certificate /etc/letsencrypt/live/ghosttunnel.space/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ghosttunnel.space/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Шаг 5: Если конфигурация неправильная, исправьте вручную

```bash
sudo nano /etc/nginx/sites-available/ghosttunnel.space
```

Полная конфигурация:

```nginx
# Редирект HTTP на HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name ghosttunnel.space www.ghosttunnel.space;
    
    # Для Let's Encrypt
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
    
    # Редирект на HTTPS
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS сервер
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ghosttunnel.space www.ghosttunnel.space;

    # SSL сертификаты
    ssl_certificate /etc/letsencrypt/live/ghosttunnel.space/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ghosttunnel.space/privkey.pem;
    
    # SSL настройки
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Проксирование на Flask
    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Таймауты для webhook'ов
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

### Шаг 6: Проверьте и перезагрузите Nginx

```bash
# Проверьте конфигурацию
sudo nginx -t

# Если все ОК, перезагрузите
sudo systemctl reload nginx

# Или перезапустите
sudo systemctl restart nginx
```

### Шаг 7: Проверьте DNS настройки

Убедитесь, что DNS правильно настроен:

```bash
# Проверьте A записи
dig ghosttunnel.space +short
nslookup ghosttunnel.space

# Должен вернуть IP адрес вашего сервера
```

### Шаг 8: Проверьте доступность

```bash
# Проверьте HTTP (должен редиректить на HTTPS)
curl -I http://ghosttunnel.space

# Проверьте HTTPS (должен работать)
curl -I https://ghosttunnel.space

# Проверьте webhook эндпоинт
curl -X POST https://ghosttunnel.space/webhook/yookassa \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'
```

### Шаг 9: Если все еще не работает

#### Проверьте firewall

```bash
# Убедитесь, что порты открыты
sudo ufw status
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

#### Проверьте логи Nginx

```bash
# Ошибки
sudo tail -f /var/log/nginx/error.log

# Доступ
sudo tail -f /var/log/nginx/access.log
```

#### Проверьте, что Flask доступен локально

```bash
# Проверьте, что Flask работает на порту 5000
curl http://localhost:5000/webhook/yookassa

# Проверьте статус Docker контейнера
sudo docker compose ps
```

## Альтернатива: Временное использование HTTP (только для тестирования)

**Внимание:** YooKassa требует HTTPS для продакшн, но для тестирования можно временно использовать HTTP.

### 1. Настройте Nginx для HTTP

```bash
sudo nano /etc/nginx/sites-available/ghosttunnel.space
```

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

### 2. Обновите .env

```bash
# Временно используйте HTTP (только для тестирования!)
WEBHOOK_URL=http://ghosttunnel.space
```

**Важно:** Это только для тестирования! Для продакшн обязательно нужен HTTPS.

## Автоматическое обновление сертификата

Certbot автоматически обновляет сертификаты. Проверьте cron:

```bash
# Проверьте, что автообновление настроено
sudo systemctl status certbot.timer

# Или проверьте cron
sudo crontab -l | grep certbot
```

## Проверка после исправления

1. ✅ `curl https://ghosttunnel.space` работает без ошибок
2. ✅ `curl https://ghosttunnel.space/webhook/yookassa` возвращает ответ
3. ✅ В браузере `https://ghosttunnel.space` открывается с зеленым замочком
4. ✅ Webhook настроен в YooKassa с HTTPS URL
5. ✅ Тестовый платеж проходит успешно

## Полезные команды

```bash
# Проверить SSL сертификат
openssl s_client -connect ghosttunnel.space:443 -servername ghosttunnel.space

# Проверить срок действия сертификата
sudo certbot certificates

# Обновить сертификат вручную
sudo certbot renew --force-renewal

# Проверить конфигурацию Nginx
sudo nginx -t

# Перезагрузить Nginx
sudo systemctl reload nginx
```

