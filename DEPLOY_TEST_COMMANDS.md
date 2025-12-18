# Команды для деплоя в тестовую среду

## Автоматический деплой через GitHub Actions

Деплой происходит автоматически при пуше в ветку `test` через workflow `.github/workflows/deploy-server2.yml`.

## Основные команды, выполняемые при деплое

### 1. Подготовка и остановка старого бота

```bash
# Создание рабочей директории
sudo mkdir -p /root/Daralla
cd /root/Daralla

# Остановка старого бота
sudo docker compose down || true
# или
sudo docker-compose down || true
```

### 2. Создание бэкапов

```bash
# Создание структуры для бэкапов
sudo mkdir -p /root/backups/data /root/backups/env
timestamp=$(date +'%Y%m%d_%H%M%S')

# Бэкап баз данных
if [ -d "data" ] && [ -n "$(ls -A data/*.db 2>/dev/null)" ]; then
  sudo tar -czf "/root/backups/data/backup_${timestamp}.tar.gz" data/*.db
  # Оставляем только 5 последних бэкапов
  ls -t /root/backups/data/backup_*.tar.gz | tail -n +6 | xargs -r sudo rm -f
fi

# Бэкап .env файла
if [ -f ".env" ]; then
  sudo cp .env "/root/backups/env/env_${timestamp}"
  ls -t /root/backups/env/env_* | tail -n +6 | xargs -r sudo rm -f
fi
```

### 3. Установка Docker и Docker Compose (если не установлены)

```bash
# Проверка и установка Docker
if ! command -v docker &> /dev/null; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq ca-certificates curl gnupg lsb-release
  sudo mkdir -p /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt-get update -qq
  sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  sudo systemctl start docker
  sudo systemctl enable docker
fi

# Установка Docker Compose (standalone, если нужно)
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
  sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
  sudo chmod +x /usr/local/bin/docker-compose
fi
```

### 4. Клонирование кода и переключение на ветку test

```bash
# Установка git и sqlite3
sudo apt-get update -qq && sudo apt-get install -y -qq git sqlite3

# Удаление старой версии и клонирование
sudo rm -rf /root/Daralla
sudo mkdir -p /root/Daralla
cd /root
sudo git clone https://thesemeiev:$GITHUB_TOKEN@github.com/thesemeiev/Daralla.git Daralla
cd /root/Daralla

# Переключение на тестовую ветку
sudo git checkout test
sudo git pull origin test
```

### 5. Восстановление данных

```bash
# Восстановление баз данных
latest_db_backup=$(ls -t /root/backups/data/backup_*.tar.gz 2>/dev/null | head -n1)
if [ -n "$latest_db_backup" ]; then
  sudo mkdir -p data
  sudo tar -xzf "$latest_db_backup" -C .
else
  # Создание пустых баз данных, если бэкапа нет
  sudo mkdir -p data
  sudo touch data/vpn_keys.db data/subscribers.db data/notifications.db data/users.db
fi

# Восстановление .env файла
latest_env=$(ls -t /root/backups/env/env_* 2>/dev/null | head -n1)
if [ -n "$latest_env" ]; then
  sudo cp "$latest_env" .env
else
  # Создание минимального .env файла, если бэкапа нет
  if [ ! -f ".env" ]; then
    cat > .env << EOF
# Telegram Bot Configuration
TELEGRAM_TOKEN=
ADMIN_ID=
# YooKassa Payment Configuration
YOOKASSA_SHOP_ID=
YOOKASSA_SECRET_KEY=
# Webhook Configuration
NGROK_AUTH_TOKEN=
WEBHOOK_URL=
# X-UI Server Configuration
XUI_HOST_LATVIA_1=
XUI_LOGIN_LATVIA_1=
XUI_PASSWORD_LATVIA_1=
EOF
  fi
fi

# Установка прав доступа
sudo chown -R 1000:1000 data/
sudo chmod -R 666 data/*.db
sudo chmod 755 data/
```

### 6. Очистка и сборка

```bash
cd /root/Daralla

# Очистка старых контейнеров и образов
sudo docker compose down || true
timeout 30 sudo docker image prune -f || true
timeout 30 sudo docker builder prune -f || true

# Сборка контейнеров
sudo docker compose build --no-cache
```

### 7. Запуск бота

```bash
# Запуск в фоновом режиме
sudo docker compose up -d

# Проверка статуса
sleep 5
sudo docker compose ps
```

### 8. Проверка после деплоя

```bash
# Проверка статуса контейнеров
sudo docker compose ps

# Просмотр логов
sudo docker compose logs -f telegram-bot

# Проверка баз данных
sudo sqlite3 data/subscribers.db "SELECT COUNT(*) FROM subscriptions;"
```

## Ручной деплой (если нужно)

Если нужно выполнить деплой вручную на сервере:

```bash
# 1. Подключитесь к серверу
ssh root@your-test-server

# 2. Перейдите в директорию проекта
cd /root/Daralla

# 3. Остановите бота
sudo docker compose down

# 4. Обновите код
sudo git checkout test
sudo git pull origin test

# 5. Пересоберите и запустите
sudo docker compose build --no-cache
sudo docker compose up -d

# 6. Проверьте логи
sudo docker compose logs -f telegram-bot
```

## Триггеры деплоя

Деплой запускается автоматически при:
- Пуш в ветку `test`
- Ручной запуск через GitHub Actions UI (workflow_dispatch)

## Секреты GitHub, необходимые для деплоя

- `TEST_SERVER_HOST` - IP или домен тестового сервера
- `TEST_SERVER_USER` - пользователь SSH (обычно `root`)
- `TEST_SERVER_PASSWORD` - пароль SSH
- `TEST_SERVER_PORT` - порт SSH (опционально, по умолчанию 22)
- `GITHUB_TOKEN` - токен для клонирования репозитория

## Важные моменты

1. **Используйте `docker compose` (с пробелом)**, а не `docker-compose` - это современная версия
2. **Бэкапы создаются автоматически** перед каждым деплоем
3. **Данные восстанавливаются** из последнего бэкапа, если он существует
4. **.env файл** должен быть настроен на сервере перед первым запуском

