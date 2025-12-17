# Следующие шаги

## 1. Проверьте конфигурацию nginx:

```bash
sudo nginx -t
```

Если ошибок нет - продолжайте.

## 2. Проверьте активные конфигурации:

```bash
ls -la /etc/nginx/sites-enabled/
```

Должен быть симлинк на `ghosttunnel.space`

## 3. Найдите папку с проектом и запустите Docker:

```bash
# Найдите docker-compose.yml
find /root -name "docker-compose.yml" 2>/dev/null
find /home -name "docker-compose.yml" 2>/dev/null

# Или проверьте где запущен контейнер
docker ps -a | grep daralla
docker inspect daralla-bot | grep -i "source\|mount"
```

## 4. Запустите контейнер:

```bash
# Перейдите в папку с проектом (замените на реальный путь)
cd /path/to/Daralla

# Запустите контейнер
docker-compose up -d

# Проверьте статус
docker-compose ps

# Проверьте логи
docker-compose logs telegram-bot | tail -20
```

## 5. Проверьте Flask:

```bash
# Должно работать
curl http://localhost:5000/sub/1b97286f426a4d0687fdc3c3
```

## 6. Перезагрузите nginx:

```bash
sudo systemctl reload nginx
```

## 7. Проверьте через домен:

```bash
curl http://ghosttunnel.space/sub/1b97286f426a4d0687fdc3c3
```

