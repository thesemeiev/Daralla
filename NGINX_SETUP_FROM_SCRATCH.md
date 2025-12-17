# Настройка nginx с нуля

## Шаг 1: Удалите старые конфигурации (если есть)

```bash
# Удалите все старые конфигурации для ghosttunnel.space
sudo rm -f /etc/nginx/sites-enabled/ghosttunnel.space
sudo rm -f /etc/nginx/sites-enabled/your-domain.com
sudo rm -f /etc/nginx/sites-available/ghosttunnel.space
sudo rm -f /etc/nginx/sites-available/your-domain.com
```

## Шаг 2: Создайте новую конфигурацию

```bash
sudo nano /etc/nginx/sites-available/ghosttunnel.space
```

Вставьте следующее содержимое:

```nginx
server {
    listen 80;
    server_name ghosttunnel.space www.ghosttunnel.space;

    # Логирование для отладки
    access_log /var/log/nginx/ghosttunnel.access.log;
    error_log /var/log/nginx/ghosttunnel.error.log;

    # Проксирование всех запросов на Flask (порт 5000)
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Таймауты
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
        
        # Буферизация
        proxy_buffering off;
    }
}
```

Сохраните файл: `Ctrl+O`, `Enter`, `Ctrl+X`

## Шаг 3: Создайте симлинк

```bash
sudo ln -s /etc/nginx/sites-available/ghosttunnel.space /etc/nginx/sites-enabled/
```

## Шаг 4: Проверьте конфигурацию

```bash
sudo nginx -t
```

Должно быть:
```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

## Шаг 5: Проверьте, что Flask работает

```bash
# Проверьте статус Docker контейнера
docker ps | grep daralla

# Если контейнер не запущен, найдите папку проекта и запустите:
# (замените /path/to/Daralla на реальный путь)
cd /path/to/Daralla
docker-compose up -d

# Проверьте логи
docker-compose logs telegram-bot | grep -i "webhook\|5000"

# Проверьте, что Flask отвечает локально
curl -v http://127.0.0.1:5000/sub/1b97286f426a4d0687fdc3c3
```

## Шаг 6: Перезагрузите nginx

```bash
sudo systemctl reload nginx
# или
sudo systemctl restart nginx
```

## Шаг 7: Проверьте работу

```bash
# Проверьте через домен
curl -v http://ghosttunnel.space/sub/1b97286f426a4d0687fdc3c3

# Проверьте логи nginx в реальном времени
sudo tail -f /var/log/nginx/ghosttunnel.access.log
sudo tail -f /var/log/nginx/ghosttunnel.error.log
```

## Шаг 8: Если все еще не работает

### Проверьте, что порт 5000 слушается:

```bash
# Проверьте, что порт открыт
netstat -tlnp | grep 5000
# или
ss -tlnp | grep 5000

# Должно показать что-то вроде:
# tcp  0  0 0.0.0.0:5000  0.0.0.0:*  LISTEN  <PID>/python
```

### Проверьте Docker порты:

```bash
docker port daralla-bot
# Должно показать: 5000/tcp -> 0.0.0.0:5000
```

### Проверьте firewall:

```bash
sudo ufw status
# Убедитесь, что порт 80 открыт
sudo ufw allow 80/tcp
```

## Готово!

После выполнения всех шагов subscription endpoint должен работать.

