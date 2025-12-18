# Исправление несоответствия домена в SSL сертификате

## Проблема
Сертификат обновлен, но все еще не соответствует домену `ghosttunnel.space`.

## Решение

### Шаг 1: Проверьте, для какого домена выдан сертификат

```bash
# Проверьте информацию о сертификате
sudo openssl x509 -in /etc/letsencrypt/live/ghosttunnel.space/fullchain.pem -text -noout | grep -A 2 "Subject Alternative Name"

# Или проверьте через certbot
sudo certbot certificates
```

### Шаг 2: Проверьте конфигурацию Nginx

```bash
# Проверьте, какой файл используется
sudo nginx -T | grep -A 10 "server_name.*ghosttunnel"

# Проверьте default конфигурацию
sudo cat /etc/nginx/sites-enabled/default

# Проверьте конфигурацию ghosttunnel.space
sudo cat /etc/nginx/sites-available/ghosttunnel.space
```

### Шаг 3: Удалите старый сертификат и создайте новый

Если сертификат был выдан для другого домена, нужно удалить и создать заново:

```bash
# Удалите старый сертификат
sudo certbot delete --cert-name ghosttunnel.space

# Создайте новый сертификат
sudo certbot certonly --nginx -d ghosttunnel.space -d www.ghosttunnel.space
```

### Шаг 4: Или переустановите сертификат правильно

```bash
# Удалите все упоминания домена
sudo rm -rf /etc/letsencrypt/live/ghosttunnel.space
sudo rm -rf /etc/letsencrypt/archive/ghosttunnel.space
sudo rm -rf /etc/letsencrypt/renewal/ghosttunnel.space.conf

# Создайте новый сертификат
sudo certbot certonly --standalone -d ghosttunnel.space -d www.ghosttunnel.space
```

### Шаг 5: Настройте Nginx вручную

Создайте/обновите конфигурацию:

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
    
    # SSL настройки (из certbot)
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

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

### Шаг 6: Создайте симлинк (если нет)

```bash
# Убедитесь, что симлинк существует
sudo ln -sf /etc/nginx/sites-available/ghosttunnel.space /etc/nginx/sites-enabled/ghosttunnel.space

# Удалите default, если он конфликтует (опционально)
# sudo rm /etc/nginx/sites-enabled/default
```

### Шаг 7: Проверьте и перезагрузите Nginx

```bash
# Проверьте конфигурацию
sudo nginx -t

# Если все ОК, перезагрузите
sudo systemctl reload nginx
```

### Шаг 8: Проверьте DNS

Убедитесь, что DNS правильно настроен:

```bash
# Проверьте A записи
dig ghosttunnel.space +short
nslookup ghosttunnel.space

# Должен вернуть IP адрес вашего сервера
```

### Шаг 9: Проверьте доступность

```bash
# С сервера (должно работать)
curl -k https://ghosttunnel.space/webhook/yookassa

# Или проверьте сертификат
openssl s_client -connect ghosttunnel.space:443 -servername ghosttunnel.space < /dev/null 2>/dev/null | openssl x509 -noout -subject -dates
```

### Шаг 10: Если все еще не работает

#### Вариант A: Используйте certbot с --nginx для автоматической настройки

```bash
# Удалите старую конфигурацию
sudo rm /etc/nginx/sites-enabled/default
sudo rm /etc/nginx/sites-enabled/ghosttunnel.space

# Создайте базовую конфигурацию
sudo nano /etc/nginx/sites-available/ghosttunnel.space
```

Минимальная конфигурация для certbot:

```nginx
server {
    listen 80;
    server_name ghosttunnel.space www.ghosttunnel.space;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

```bash
# Создайте симлинк
sudo ln -s /etc/nginx/sites-available/ghosttunnel.space /etc/nginx/sites-enabled/ghosttunnel.space

# Перезагрузите Nginx
sudo systemctl reload nginx

# Запустите certbot с --nginx (он автоматически обновит конфигурацию)
sudo certbot --nginx -d ghosttunnel.space -d www.ghosttunnel.space
```

#### Вариант B: Проверьте, что сертификат действительно для правильного домена

```bash
# Проверьте Subject Alternative Name в сертификате
sudo openssl x509 -in /etc/letsencrypt/live/ghosttunnel.space/fullchain.pem -text -noout | grep -A 1 "Subject Alternative Name"

# Должно быть:
# DNS:ghosttunnel.space, DNS:www.ghosttunnel.space
```

Если там другой домен, значит сертификат был выдан для другого домена. Нужно удалить и создать заново.

## Альтернативное решение: Проверьте, не используется ли другой домен

Возможно, сертификат был выдан для другого домена. Проверьте:

```bash
# Посмотрите все сертификаты
sudo certbot certificates

# Проверьте, какие домены в сертификате
sudo openssl x509 -in /etc/letsencrypt/live/ghosttunnel.space/fullchain.pem -text -noout | grep DNS
```

## После исправления

1. ✅ `curl https://ghosttunnel.space` работает
2. ✅ `curl https://ghosttunnel.space/webhook/yookassa` работает
3. ✅ В браузере нет предупреждений SSL
4. ✅ Webhook настроен в YooKassa

