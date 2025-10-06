#!/bin/bash

# Скрипт для обновления существующего бота до новой версии с CI/CD
# Запустите на сервере: bash update-existing-bot.sh

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

log "🔄 Обновление существующего бота до новой версии с CI/CD"

# Проверяем, что мы в правильной директории
if [ ! -f "docker-compose.yml" ]; then
    error "Запустите из папки с ботом (где есть docker-compose.yml)"
fi

# Создаем резервную копию текущего состояния
log "📦 Создаю резервную копию текущего состояния..."
BACKUP_NAME="before_update_$(date +'%Y%m%d_%H%M%S')"
mkdir -p backups
tar -czf "backups/${BACKUP_NAME}.tar.gz" . --exclude='backups' --exclude='.git'
success "Резервная копия создана: backups/${BACKUP_NAME}.tar.gz"

# Останавливаем текущий бот
log "🛑 Останавливаю текущий бот..."
docker-compose down 2>/dev/null || warning "Бот не был запущен"

# Сохраняем текущий .env файл
if [ -f ".env" ]; then
    log "💾 Сохраняю текущий .env файл..."
    cp .env .env.backup
    success ".env файл сохранен как .env.backup"
else
    warning ".env файл не найден! Создайте его из env.example"
fi

# Сохраняем текущие базы данных
if [ -d "data" ]; then
    log "💾 Сохраняю текущие базы данных..."
    cp -r data data.backup
    success "Базы данных сохранены в data.backup"
else
    warning "Папка data не найдена!"
fi

# Обновляем код из Git
log "📥 Обновляю код из Git..."
git fetch origin
git reset --hard origin/main
success "Код обновлен"

# Восстанавливаем .env файл
if [ -f ".env.backup" ]; then
    log "🔄 Восстанавливаю .env файл..."
    cp .env.backup .env
    success ".env файл восстановлен"
fi

# Восстанавливаем базы данных
if [ -d "data.backup" ]; then
    log "🔄 Восстанавливаю базы данных..."
    rm -rf data
    mv data.backup data
    success "Базы данных восстановлены"
fi

# Проверяем .env файл
if [ ! -f ".env" ]; then
    log "📝 Создаю .env файл из примера..."
    cp env.example .env
    warning "Создан .env файл из примера. ОТРЕДАКТИРУЙТЕ ЕГО с вашими настройками!"
fi

# Устанавливаем права на скрипты
log "🔐 Устанавливаю права на скрипты..."
chmod +x *.sh 2>/dev/null || true

# Собираем новый образ
log "🏗️ Собираю новый образ..."
docker-compose build --no-cache

# Запускаем обновленный бот
log "🚀 Запускаю обновленный бот..."
docker-compose up -d

# Ждем запуска
log "⏳ Жду запуска..."
sleep 10

# Проверяем статус
if docker-compose ps | grep -q "Up"; then
    success "✅ Бот успешно обновлен и запущен!"
    
    log "📋 Статус:"
    docker-compose ps
    
    log "📋 Последние логи:"
    docker-compose logs --tail=10
    
else
    error "❌ Ошибка запуска. Логи: docker-compose logs"
fi

echo ""
success "🎉 Обновление завершено!"
echo "💡 Команды для управления:"
echo "   Логи:    docker-compose logs -f"
echo "   Стоп:    docker-compose down"
echo "   Рестарт: docker-compose restart"
echo "   Статус:  docker-compose ps"
echo ""
echo "🔄 Для отката (если что-то пошло не так):"
echo "   tar -xzf backups/${BACKUP_NAME}.tar.gz"
