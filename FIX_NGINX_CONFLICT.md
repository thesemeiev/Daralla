# Исправление конфликта конфигураций Nginx

## Проблема
Есть два server block для `ghosttunnel.space`:
- В `default` - с SSL (443)
- В `ghosttunnel.space` - только HTTP (80), без SSL

## Решение

### Шаг 1: Добавьте SSL в ghosttunnel.space

```bash
sudo nano /etc/nginx/sites-available/ghosttunnel.space
```

Обновите файл:

```nginx
# Редирект HTTP на HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name ghosttunnel.space www.ghosttunnel.space;

    access_log /var/log/nginx/ghosttunnel.access.log;
    error_log /var/log/nginx/ghosttunnel.error.log;

    # Редирект на HTTPS
    return 301 https://$server_name$request_uri;
}

# HTTPS сервер
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ghosttunnel.space www.ghosttunnel.space;

    access_log /var/log/nginx/ghosttunnel.access.log;
    error_log /var/log/nginx/ghosttunnel.error.log;

    # SSL сертификаты
    ssl_certificate /etc/letsencrypt/live/ghosttunnel.space/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ghosttunnel.space/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        proxy_buffering off;
    }
}
```

### Шаг 2: Удалите конфликтующий блок из default

```bash
sudo nano /etc/nginx/sites-enabled/default
```

Найдите и удалите или закомментируйте блоки с `ghosttunnel.space`. Или проще - удалите default:

```bash
# Удалите default (если не нужен для других сайтов)
sudo rm /etc/nginx/sites-enabled/default
```

### Шаг 3: Убедитесь, что ghosttunnel.space активен

```bash
# Проверьте симлинк
ls -la /etc/nginx/sites-enabled/ghosttunnel.space

# Если нет, создайте
sudo ln -sf /etc/nginx/sites-available/ghosttunnel.space /etc/nginx/sites-enabled/ghosttunnel.space
```

### Шаг 4: Проверьте и перезагрузите

```bash
# Проверьте конфигурацию
sudo nginx -t

# Должно быть без предупреждений о конфликтах

# Перезагрузите
sudo systemctl reload nginx
```

### Шаг 5: Проверьте

```bash
# Проверьте доступность
curl https://ghosttunnel.space/webhook/yookassa

# Должно работать без ошибок SSL!
```

