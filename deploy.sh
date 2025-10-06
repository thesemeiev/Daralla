#!/bin/bash

# Скрипт деплоя Daralla Bot для Linux
# Использование: ./deploy.sh 

set -e

echo "🚀 Daralla Bot - Деплой"

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

# Проверки
[ ! -f "docker-compose.yml" ] && error "Запустите из корня проекта"

if [ ! -f ".env" ]; then
    if [ -f "env.example" ]; then
        log "Создаю .env из примера..."
        cp env.example .env
        error "Файл .env создан из примера. Отредактируйте его с вашими настройками и запустите скрипт снова!"
    else
        error "Создайте .env файл"
    fi
fi

# Загружаем переменные
source .env

# Проверяем настройки
if [ -z "$BOT_TOKEN" ] || [ "$BOT_TOKEN" = "your_telegram_bot_token_here" ]; then
    error "Настройте BOT_TOKEN в .env файле"
fi

if [ -z "$ADMIN_ID" ] || [ "$ADMIN_ID" = "your_admin_telegram_id_here" ]; then
    error "Настройте ADMIN_ID в .env файле"
fi

# Проверяем конфигурацию серверов (предупреждение, не ошибка)
if [ -z "$XUI_HOST_FINLAND" ] || [ -z "$XUI_LOGIN_FINLAND" ] || [ -z "$XUI_PASSWORD_FINLAND" ]; then
    warning "Сервер Finland не настроен полностью"
fi

if [ -z "$XUI_HOST_LATVIA" ] || [ -z "$XUI_LOGIN_LATVIA" ] || [ -z "$XUI_PASSWORD_LATVIA" ]; then
    warning "Сервер Latvia не настроен полностью"
fi

if [ -z "$XUI_HOST_ESTONIA" ] || [ -z "$XUI_LOGIN_ESTONIA" ] || [ -z "$XUI_PASSWORD_ESTONIA" ]; then
    warning "Сервер Estonia не настроен полностью"
fi

log "Настройки проверены: BOT_TOKEN и ADMIN_ID заданы"

# Проверяем Docker
command -v docker >/dev/null 2>&1 || error "Установите Docker"

# Проверяем docker-compose и исправляем права доступа
if ! command -v docker-compose >/dev/null 2>&1; then
    # Пробуем docker compose (новая версия)
    if docker compose version >/dev/null 2>&1; then
        log "Используем docker compose (новая версия)"
        DOCKER_COMPOSE_CMD="docker compose"
    else
        # Проверяем права доступа к docker-compose
        if [ -f "/usr/local/bin/docker-compose" ]; then
            log "Исправляю права доступа к docker-compose..."
            sudo chmod +x /usr/local/bin/docker-compose
        fi
        command -v docker-compose >/dev/null 2>&1 || error "Установите Docker Compose"
        DOCKER_COMPOSE_CMD="docker-compose"
    fi
else
    DOCKER_COMPOSE_CMD="docker-compose"
fi

log "Используем команду: $DOCKER_COMPOSE_CMD"

# Обновление кода
if [ "$1" = "update" ]; then
    log "Обновляю код..."
    git pull origin main || warning "Не удалось обновить"
fi

# Останавливаем и удаляем старый контейнер
log "Останавливаю старый контейнер..."
$DOCKER_COMPOSE_CMD down 2>/dev/null || true

# Удаляем старый образ
log "Удаляю старый образ..."
docker image rm daralla_telegram-bot 2>/dev/null || true

# Собираем и запускаем
log "Собираю образ..."
$DOCKER_COMPOSE_CMD build --no-cache

log "Запускаю бота..."
$DOCKER_COMPOSE_CMD up -d

# Ждем запуска
sleep 3

# Проверяем статус
if $DOCKER_COMPOSE_CMD ps | grep -q "Up"; then
    success "Бот запущен!"
else
    error "Ошибка запуска. Логи: $DOCKER_COMPOSE_CMD logs"
fi

echo ""
log "Статус:"
$DOCKER_COMPOSE_CMD ps

echo ""
log "Логи:"
$DOCKER_COMPOSE_CMD logs --tail=10

echo ""
success "Готово!"
echo "💡 Команды:"
echo "   Логи:    $DOCKER_COMPOSE_CMD logs -f"
echo "   Стоп:    $DOCKER_COMPOSE_CMD down"
echo "   Обновить: ./deploy.sh update"
