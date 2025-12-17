# Настройка домена для subscription links

## Шаг 1: Настройка DNS

1. Добавьте A-запись в DNS вашего домена:
   ```
   Тип: A
   Имя: @ (или your-domain.com)
   Значение: IP_адрес_вашего_сервера
   TTL: 3600
   ```

2. (Опционально) Добавьте CNAME для www:
   ```
   Тип: CNAME
   Имя: www
   Значение: your-domain.com
   TTL: 3600
   ```

## Шаг 2: Установка Nginx

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install nginx

# Проверьте статус
sudo systemctl status nginx
```

## Шаг 3: Настройка Nginx

1. Скопируйте конфигурацию:
```bash
sudo cp nginx.conf.example /etc/nginx/sites-available/your-domain.com
```

2. Отредактируйте файл:
```bash
sudo nano /etc/nginx/sites-available/your-domain.com
```

Замените `your-domain.com` на ваш домен.

3. Создайте симлинк:
```bash
sudo ln -s /etc/nginx/sites-available/your-domain.com /etc/nginx/sites-enabled/
```

4. Проверьте конфигурацию:
```bash
sudo nginx -t
```

5. Перезагрузите Nginx:
```bash
sudo systemctl reload nginx
```

## Шаг 4: Настройка SSL (HTTPS) - Рекомендуется

### Вариант A: Let's Encrypt (бесплатно)

1. Установите certbot:
```bash
sudo apt install certbot python3-certbot-nginx
```

2. Получите SSL сертификат:
```bash
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
```

3. Certbot автоматически обновит конфигурацию Nginx и настроит HTTPS.

4. Автоматическое обновление (уже настроено в certbot):
```bash
# Проверьте, что таймер работает
sudo systemctl status certbot.timer
```

### Вариант B: Cloudflare (если используете Cloudflare)

1. Включите "Full" или "Full (strict)" SSL режим в Cloudflare
2. Cloudflare автоматически предоставит SSL сертификат

## Шаг 5: Настройка .env файла

Добавьте в ваш `.env` файл:

```bash
# Для HTTP (временно, для тестирования)
WEBHOOK_URL=http://your-domain.com

# Для HTTPS (рекомендуется для продакшена)
WEBHOOK_URL=https://your-domain.com
```

## Шаг 6: Перезапуск бота

```bash
docker-compose down
docker-compose up -d
```

## Шаг 7: Проверка

1. Проверьте, что webhook сервер доступен:
```bash
curl http://your-domain.com/webhook/yookassa
# Должен вернуть 405 Method Not Allowed (это нормально, endpoint работает)
```

2. Проверьте subscription endpoint:
```bash
curl http://your-domain.com/sub/test-token
# Должен вернуть 404 или 403 (подписка не найдена - это нормально)
```

## Важные моменты

1. **Порт 5000**: Убедитесь, что порт 5000 открыт в firewall:
```bash
sudo ufw allow 5000/tcp
# Или если используете iptables
sudo iptables -A INPUT -p tcp --dport 5000 -j ACCEPT
```

2. **Безопасность**: 
   - Используйте HTTPS в продакшене
   - Настройте firewall (откройте только 80, 443, и SSH)
   - Регулярно обновляйте систему

3. **Мониторинг**:
   - Проверяйте логи Nginx: `sudo tail -f /var/log/nginx/error.log`
   - Проверяйте логи бота: `docker-compose logs -f telegram-bot`

## Troubleshooting

### Проблема: 502 Bad Gateway
- Проверьте, что бот запущен: `docker-compose ps`
- Проверьте, что порт 5000 открыт: `netstat -tlnp | grep 5000`
- Проверьте логи: `docker-compose logs telegram-bot`

### Проблема: DNS не резолвится
- Подождите 5-10 минут после изменения DNS
- Проверьте DNS: `nslookup your-domain.com`
- Используйте `dig your-domain.com` для детальной информации

### Проблема: SSL не работает
- Убедитесь, что порты 80 и 443 открыты
- Проверьте, что DNS правильно настроен
- Проверьте логи certbot: `sudo certbot certificates`

## Пример итоговой конфигурации

После настройки SSL ваш `.env` должен содержать:
```bash
WEBHOOK_URL=https://your-domain.com
```

И subscription links будут выглядеть так:
```
https://your-domain.com/sub/1b97286f426a4d0687fdc3c3
```

Пользователи смогут использовать эту ссылку в VPN клиентах для автоматического импорта всех серверов подписки.

