# Обновление переменных окружения в Docker

## Проблема
После изменения `.env` файла Docker контейнер продолжает использовать старые переменные.

## Решение

### Вариант 1: Пересоздать контейнер (рекомендуется)

```bash
cd /root/Daralla

# Остановите и удалите контейнер
sudo docker compose down

# Пересоздайте и запустите с новыми переменными
sudo docker compose up -d
```

### Вариант 2: Пересобрать контейнер

```bash
cd /root/Daralla

# Остановите контейнер
sudo docker compose stop

# Пересоберите (если нужно)
sudo docker compose build --no-cache

# Запустите заново
sudo docker compose up -d
```

### Вариант 3: Перезапустить с пересозданием

```bash
cd /root/Daralla

# Пересоздать контейнер (без пересборки образа)
sudo docker compose up -d --force-recreate
```

### Вариант 4: Полная пересборка

```bash
cd /root/Daralla

# Остановите и удалите все
sudo docker compose down

# Удалите старые образы (опционально)
sudo docker compose down --rmi all

# Пересоберите и запустите
sudo docker compose up -d --build
```

## Проверка переменных в контейнере

После перезапуска проверьте, что переменные обновились:

```bash
# Проверьте переменные внутри контейнера
sudo docker compose exec telegram-bot env | grep WEBHOOK_URL
sudo docker compose exec telegram-bot env | grep TELEGRAM_TOKEN
```

## Проверка .env файла

Убедитесь, что файл обновлен:

```bash
# Проверьте содержимое .env
cat .env | grep WEBHOOK_URL

# Должно быть:
# WEBHOOK_URL=https://ghosttunnel.space
```

## Важно

- Docker Compose читает `.env` файл при запуске (`docker compose up`)
- Простой `restart` не перечитывает `.env` файл
- Нужно использовать `down` и `up` для пересоздания контейнера

## Быстрая команда

```bash
cd /root/Daralla && sudo docker compose down && sudo docker compose up -d
```

