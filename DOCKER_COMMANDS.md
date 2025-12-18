# Docker команды для тестового сервера

## Важно: Используйте `docker compose` (с пробелом), а не `docker-compose`

На сервере установлен Docker Compose как плагин (новая версия), поэтому команды немного другие.

## Основные команды:

### Остановить контейнер:
```bash
sudo docker compose stop
# или
sudo docker compose down
```

### Запустить контейнер:
```bash
sudo docker compose up -d
```

### Перезапустить контейнер:
```bash
sudo docker compose restart
```

### Посмотреть статус:
```bash
sudo docker compose ps
```

### Посмотреть логи:
```bash
sudo docker compose logs -f telegram-bot
```

### Пересобрать и перезапустить:
```bash
sudo docker compose down
sudo docker compose build --no-cache
sudo docker compose up -d
```

### Проверить версию:
```bash
docker compose version
```

## Если нужно установить старую версию docker-compose:

```bash
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

Но лучше использовать `docker compose` (плагин) - это современный способ.

