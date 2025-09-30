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

log "Настройки проверены: BOT_TOKEN и ADMIN_ID заданы"

# Проверяем Docker
command -v docker >/dev/null 2>&1 || error "Установите Docker"
command -v docker-compose >/dev/null 2>&1 || error "Установите Docker Compose"

# Обновление кода
if [ "$1" = "update" ]; then
    log "Обновляю код..."
    git pull origin main || warning "Не удалось обновить"
fi

# Останавливаем и удаляем старый контейнер
log "Останавливаю старый контейнер..."
docker-compose down 2>/dev/null || true

# Удаляем старый образ
log "Удаляю старый образ..."
docker image rm daralla_telegram-bot 2>/dev/null || true

# Собираем и запускаем
log "Собираю образ..."
docker-compose build --no-cache

log "Запускаю бота..."
docker-compose up -d

# Ждем запуска
sleep 3

# Проверяем статус
if docker-compose ps | grep -q "Up"; then
    success "Бот запущен!"
else
    error "Ошибка запуска. Логи: docker-compose logs"
fi

echo ""
log "Статус:"
docker-compose ps

echo ""
log "Логи:"
docker-compose logs --tail=10

echo ""
success "Готово!"
echo "💡 Команды:"
echo "   Логи:    docker-compose logs -f"
echo "   Стоп:    docker-compose down"
echo "   Обновить: ./deploy.sh update"
