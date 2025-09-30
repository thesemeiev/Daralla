#!/bin/bash

# Универсальный скрипт для деплоя Daralla Bot
# Использование: ./deploy.sh [update]

set -e  # Остановка при ошибке

echo "🚀 Daralla Bot - Деплой на сервер"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для логирования
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Проверяем, что мы в правильной директории
if [ ! -f "docker-compose.yml" ]; then
    error "docker-compose.yml не найден. Запустите скрипт из корня проекта."
fi

# Проверяем наличие .env файла
if [ ! -f ".env" ]; then
    if [ -f "env.example" ]; then
        log "Создаем .env файл из примера..."
        cp env.example .env
        warning "Файл .env создан из примера. Отредактируйте его с вашими настройками!"
    else
        error "Файл .env не найден. Создайте его с необходимыми переменными окружения."
    fi
fi

# Загружаем переменные окружения
source .env

# Проверяем обязательные переменные
if [ -z "$BOT_TOKEN" ] || [ "$BOT_TOKEN" = "your_telegram_bot_token_here" ]; then
    error "BOT_TOKEN не настроен в файле .env"
fi

if [ -z "$ADMIN_ID" ] || [ "$ADMIN_ID" = "your_admin_telegram_id_here" ]; then
    error "ADMIN_ID не настроен в файле .env"
fi

# Проверяем наличие Docker
if ! command -v docker &> /dev/null; then
    error "Docker не установлен. Установите Docker и попробуйте снова."
fi

# Проверяем наличие docker-compose
if ! command -v docker-compose &> /dev/null; then
    error "Docker Compose не установлен. Установите Docker Compose и попробуйте снова."
fi

# Если передан аргумент "update", обновляем код
if [ "$1" = "update" ]; then
    log "Обновляем код из репозитория..."
    git pull origin main || warning "Не удалось обновить код из Git"
fi

# Останавливаем существующий контейнер
log "Останавливаем существующий контейнер..."
docker-compose down || warning "Контейнер не был запущен"

# Удаляем старый образ для полной пересборки
log "Удаляем старый образ..."
docker image rm daralla_telegram-bot 2>/dev/null || warning "Старый образ не найден"

# Собираем новый образ
log "Собираем Docker образ..."
docker-compose build --no-cache

# Запускаем контейнер
log "Запускаем бота..."
docker-compose up -d

# Ждем запуска контейнера
sleep 5

# Проверяем статус
log "Проверяем статус контейнера..."
if docker-compose ps | grep -q "Up"; then
    success "Бот успешно запущен!"
else
    error "Не удалось запустить бота. Проверьте логи: docker-compose logs"
fi

# Показываем статус
echo ""
log "Статус контейнера:"
docker-compose ps

# Показываем последние логи
echo ""
log "Последние логи (последние 20 строк):"
docker-compose logs --tail=20

# Показываем полезные команды
echo ""
success "Деплой завершен!"
echo ""
echo "💡 Полезные команды:"
echo "   Просмотр логов:     docker-compose logs -f"
echo "   Остановка бота:     docker-compose down"
echo "   Перезапуск:         docker-compose restart"
echo "   Обновление:         ./deploy.sh update"
echo "   Статус:             docker-compose ps"
echo ""
