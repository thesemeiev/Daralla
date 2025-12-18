# Проверка конфигурации Nginx для SSL

## ✅ Сертификат правильный!

Сертификат выдан для правильного домена. Проблема в конфигурации Nginx.

## Шаг 1: Проверьте, какая конфигурация активна

```bash
# Посмотрите все активные конфигурации
ls -la /etc/nginx/sites-enabled/

# Проверьте, какой server block обрабатывает ghosttunnel.space
sudo nginx -T | grep -B 5 -A 15 "server_name.*ghosttunnel"
```

## Шаг 2: Проверьте конфигурацию default

Certbot обновил `/etc/nginx/sites-enabled/default`. Проверьте его:

```bash
sudo cat /etc/nginx/sites-enabled/default
```

## Шаг 3: Проверьте конфигурацию ghosttunnel.space

```bash
sudo cat /etc/nginx/sites-available/ghosttunnel.space
```

## Шаг 4: Убедитесь, что правильный файл используется

Если certbot обновил `default`, но у вас есть отдельный файл для `ghosttunnel.space`, нужно:

### Вариант A: Использовать default (если он правильно настроен)

```bash
# Проверьте, что в default правильный server_name
sudo cat /etc/nginx/sites-enabled/default | grep -A 20 "server_name.*ghosttunnel"
```

Если там правильный `server_name ghosttunnel.space` и правильные SSL настройки - все должно работать.

### Вариант B: Использовать отдельный файл ghosttunnel.space

```bash
# Убедитесь, что файл существует
sudo cat /etc/nginx/sites-available/ghosttunnel.space

# Создайте симлинк (если нет)
sudo ln -sf /etc/nginx/sites-available/ghosttunnel.space /etc/nginx/sites-enabled/ghosttunnel.space

# Удалите default, если он конфликтует
sudo rm /etc/nginx/sites-enabled/default
```

## Шаг 5: Обновите конфигурацию ghosttunnel.space

Если используете отдельный файл, обновите его:

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
    return 301 https://$server_name$request_uri;
}

# HTTPS сервер
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ghosttunnel.space www.ghosttunnel.space;

    # SSL сертификаты (правильные пути)
    ssl_certificate /etc/letsencrypt/live/ghosttunnel.space/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ghosttunnel.space/privkey.pem;
    
    # SSL настройки из certbot
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    # Проксирование на Flask
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

## Шаг 6: Проверьте конфигурацию

```bash
# Проверьте синтаксис
sudo nginx -t

# Проверьте, что правильный сертификат используется
sudo nginx -T | grep -A 2 "server_name.*ghosttunnel" | grep ssl_certificate
```

Должно быть:
```
ssl_certificate /etc/letsencrypt/live/ghosttunnel.space/fullchain.pem;
```

## Шаг 7: Перезагрузите Nginx

```bash
sudo systemctl reload nginx
```

## Шаг 8: Проверьте доступность

```bash
# С сервера
curl -v https://ghosttunnel.space/webhook/yookassa 2>&1 | grep -i "ssl\|certificate\|subject"

# Должно показать правильный сертификат
```

## Шаг 9: Если все еще не работает

### Проверьте, нет ли конфликта конфигураций

```bash
# Посмотрите все server blocks
sudo nginx -T | grep -E "server_name|ssl_certificate" | head -20

# Убедитесь, что только один server block обрабатывает ghosttunnel.space
```

### Проверьте логи Nginx

```bash
# Ошибки
sudo tail -20 /var/log/nginx/error.log

# Доступ
sudo tail -20 /var/log/nginx/access.log
```

### Проверьте, что Flask доступен

```bash
# Локально
curl http://localhost:5000/webhook/yookassa

# Должен вернуть ответ (даже если ошибка)
```

## Быстрое решение: Используйте default конфигурацию

Если certbot обновил default и там правильные настройки:

```bash
# Проверьте default
sudo cat /etc/nginx/sites-enabled/default

# Если там есть правильный server block для ghosttunnel.space с SSL - все должно работать
# Просто перезагрузите Nginx
sudo systemctl reload nginx
```

