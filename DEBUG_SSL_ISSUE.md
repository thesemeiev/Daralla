# Отладка проблемы SSL

## Проверьте текущую конфигурацию

```bash
# 1. Проверьте, что файл сохранен правильно
sudo cat /etc/nginx/sites-available/ghosttunnel.space

# 2. Проверьте, что симлинк существует
ls -la /etc/nginx/sites-enabled/ghosttunnel.space

# 3. Проверьте, какая конфигурация активна для 443 порта
sudo nginx -T | grep -A 20 "listen.*443.*ssl" | grep -A 20 "ghosttunnel"

# 4. Проверьте, какой сертификат используется
sudo nginx -T | grep -B 5 -A 10 "server_name.*ghosttunnel" | grep ssl_certificate
```

## Если конфигурация не применилась

Возможно, нужно перезапустить Nginx полностью:

```bash
sudo systemctl restart nginx
```

## Проверьте логи

```bash
# Проверьте ошибки Nginx
sudo tail -20 /var/log/nginx/error.log

# Проверьте доступ
sudo tail -20 /var/log/nginx/access.log
```

## Альтернативное решение: Используйте certbot для автоматической настройки

```bash
# Certbot автоматически настроит SSL
sudo certbot --nginx -d ghosttunnel.space -d www.ghosttunnel.space
```

Но сначала нужно убрать SSL блок из ghosttunnel.space, оставить только HTTP:

```bash
sudo nano /etc/nginx/sites-available/ghosttunnel.space
```

Временно оставьте только HTTP:

```nginx
server {
    listen 80;
    server_name ghosttunnel.space www.ghosttunnel.space;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

Затем запустите certbot:

```bash
sudo certbot --nginx -d ghosttunnel.space -d www.ghosttunnel.space
```

Certbot автоматически добавит SSL и обновит конфигурацию.

