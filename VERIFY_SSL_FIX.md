# Проверка после обновления SSL сертификата

## ✅ Сертификат успешно обновлен!

Certbot обновил сертификат, но развернул его в `/etc/nginx/sites-enabled/default`. 
Нужно проверить, что правильная конфигурация используется.

## Шаг 1: Проверьте конфигурацию Nginx

```bash
# Проверьте, какой файл активен
ls -la /etc/nginx/sites-enabled/

# Проверьте содержимое default
sudo cat /etc/nginx/sites-enabled/default

# Проверьте конфигурацию ghosttunnel.space
sudo cat /etc/nginx/sites-available/ghosttunnel.space
```

## Шаг 2: Убедитесь, что правильный файл используется

Если certbot обновил `default`, но у вас есть отдельный файл для `ghosttunnel.space`:

```bash
# Проверьте, есть ли симлинк
ls -la /etc/nginx/sites-enabled/ghosttunnel.space

# Если нет, создайте симлинк
sudo ln -s /etc/nginx/sites-available/ghosttunnel.space /etc/nginx/sites-enabled/ghosttunnel.space

# Или скопируйте SSL настройки из default в ghosttunnel.space
```

## Шаг 3: Обновите конфигурацию ghosttunnel.space

Если нужно, обновите файл вручную:

```bash
sudo nano /etc/nginx/sites-available/ghosttunnel.space
```

Добавьте SSL настройки:

```nginx
server {
    listen 443 ssl http2;
    server_name ghosttunnel.space www.ghosttunnel.space;

    # SSL сертификаты (обновлены certbot)
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

## Шаг 4: Проверьте и перезагрузите Nginx

```bash
# Проверьте конфигурацию
sudo nginx -t

# Если все ОК, перезагрузите
sudo systemctl reload nginx
```

## Шаг 5: Проверьте доступность HTTPS

```bash
# Проверьте основной домен
curl -I https://ghosttunnel.space

# Проверьте webhook эндпоинт
curl -X POST https://ghosttunnel.space/webhook/yookassa \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'
```

Должно работать без ошибок SSL!

## Шаг 6: Проверьте в браузере

Откройте в браузере:
- `https://ghosttunnel.space`
- Должен быть зеленый замочек 🔒
- Не должно быть предупреждений о сертификате

## Шаг 7: Настройте Webhook в YooKassa

1. Зайдите в [личный кабинет YooKassa](https://yookassa.ru/my/webhooks)
2. Добавьте/обновите webhook:
   - **URL:** `https://ghosttunnel.space/webhook/yookassa`
   - **События:** `payment.succeeded`
3. Сохраните

## Шаг 8: Проверьте .env файл

Убедитесь, что в `.env` правильный URL:

```bash
cd /root/Daralla
cat .env | grep WEBHOOK_URL
```

Должно быть:
```
WEBHOOK_URL=https://ghosttunnel.space
```

## Шаг 9: Перезапустите бота (если нужно)

```bash
sudo docker compose restart
```

## Шаг 10: Протестируйте платеж

1. Создайте тестовый платеж через бота
2. Проверьте логи:
   ```bash
   sudo docker compose logs -f telegram-bot | grep WEBHOOK
   ```
3. Должны появиться сообщения о получении webhook'а

## Если все еще есть проблемы

### Проверьте логи Nginx

```bash
# Ошибки
sudo tail -f /var/log/nginx/error.log

# Доступ
sudo tail -f /var/log/nginx/access.log
```

### Проверьте, что Flask доступен

```bash
# Локально
curl http://localhost:5000/webhook/yookassa

# Через HTTPS
curl https://ghosttunnel.space/webhook/yookassa
```

### Проверьте статус контейнера

```bash
sudo docker compose ps
sudo docker compose logs telegram-bot
```

