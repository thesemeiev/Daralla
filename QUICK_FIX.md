# Быстрое исправление

## Проблема 1: Битая симлинк

```bash
# Удалите битую симлинк
sudo rm /etc/nginx/sites-enabled/your-domain.com

# Проверьте конфигурацию
sudo nginx -t

# Должно быть: "syntax is ok" и "test is successful"
```

## Проблема 2: Flask не работает на порту 5000

```bash
# 1. Проверьте, запущен ли контейнер
docker-compose ps

# 2. Если не запущен - запустите
cd /path/to/Daralla  # Перейдите в папку с проектом
docker-compose up -d

# 3. Проверьте логи
docker-compose logs telegram-bot | grep -i "webhook\|5000\|flask"

# 4. Проверьте, что порт проброшен
docker port daralla-bot

# Должно показать: 5000/tcp -> 0.0.0.0:5000
```

## После исправления:

```bash
# 1. Проверьте Flask локально
curl http://localhost:5000/sub/1b97286f426a4d0687fdc3c3

# 2. Перезагрузите nginx
sudo systemctl reload nginx

# 3. Проверьте через домен
curl http://ghosttunnel.space/sub/1b97286f426a4d0687fdc3c3
```

