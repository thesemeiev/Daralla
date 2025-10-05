#!/bin/bash

# Скрипт для автоматического деплоя на сервер через CI/CD
# Использование: ./deploy-server.sh [environment]

set -e

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

# Переменные окружения
ENVIRONMENT=${1:-production}
PROJECT_DIR="/home/$(whoami)/Daralla"
BACKUP_DIR="$PROJECT_DIR/backups"

log "🚀 Начинаю деплой в окружении: $ENVIRONMENT"

# Проверяем, что мы в правильной директории
if [ ! -f "docker-compose.yml" ]; then
    error "Запустите из корня проекта"
fi

# Создаем резервную копию
log "📦 Создаю резервную копию..."
mkdir -p "$BACKUP_DIR"
BACKUP_NAME="pre_deploy_$(date +'%Y%m%d_%H%M%S')"
./backup.sh "$BACKUP_NAME"

# Проверяем переменные окружения
if [ ! -f ".env" ]; then
    if [ -f ".env.$ENVIRONMENT" ]; then
        log "Копирую .env.$ENVIRONMENT в .env"
        cp ".env.$ENVIRONMENT" ".env"
    else
        error "Файл .env не найден. Создайте .env или .env.$ENVIRONMENT"
    fi
fi

# Загружаем переменные
source .env

# Проверяем обязательные переменные
if [ -z "$BOT_TOKEN" ] || [ "$BOT_TOKEN" = "your_telegram_bot_token_here" ]; then
    error "Настройте BOT_TOKEN в .env файле"
fi

if [ -z "$ADMIN_ID" ] || [ "$ADMIN_ID" = "your_admin_telegram_id_here" ]; then
    error "Настройте ADMIN_ID в .env файле"
fi

log "✅ Переменные окружения проверены"

# Останавливаем старый контейнер
log "🛑 Останавливаю старый контейнер..."
docker-compose down 2>/dev/null || warning "Контейнер не был запущен"

# Удаляем старый образ
log "🗑️ Удаляю старый образ..."
docker image rm daralla_telegram-bot 2>/dev/null || warning "Образ не найден"

# Собираем новый образ
log "🏗️ Собираю новый образ..."
docker-compose build --no-cache

# Запускаем новый контейнер
log "🚀 Запускаю новый контейнер..."
docker-compose up -d

# Ждем запуска
log "⏳ Жду запуска контейнера..."
sleep 10

# Проверяем статус
if docker-compose ps | grep -q "Up"; then
    success "✅ Бот успешно запущен!"
    
    # Показываем логи
    log "📋 Последние логи:"
    docker-compose logs --tail=20
    
    # Проверяем здоровье
    log "🏥 Проверяю здоровье бота..."
    sleep 5
    
    if docker-compose ps | grep -q "Up"; then
        success "✅ Бот работает стабильно!"
    else
        error "❌ Бот не запустился корректно"
    fi
    
else
    error "❌ Ошибка запуска. Логи: docker-compose logs"
fi

# Показываем финальный статус
echo ""
log "📊 Финальный статус:"
docker-compose ps

echo ""
success "🎉 Деплой завершен успешно!"
echo "💡 Команды для управления:"
echo "   Логи:    docker-compose logs -f"
echo "   Стоп:    docker-compose down"
echo "   Рестарт: docker-compose restart"
echo "   Статус:  docker-compose ps"
