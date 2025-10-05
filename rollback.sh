#!/bin/bash

# Скрипт для отката к предыдущей версии
# Использование: ./rollback.sh [backup_name]

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

BACKUP_DIR="./backups"

log "🔄 Начинаю откат..."

# Проверяем наличие папки с бэкапами
if [ ! -d "$BACKUP_DIR" ]; then
    error "Папка с бэкапами не найдена: $BACKUP_DIR"
fi

# Если не указан конкретный бэкап, берем последний
if [ -z "$1" ]; then
    log "Поиск последнего бэкапа..."
    LATEST_BACKUP=$(ls -t "$BACKUP_DIR"/backup_*.tar.gz 2>/dev/null | head -n1)
    
    if [ -z "$LATEST_BACKUP" ]; then
        error "Бэкапы не найдены в $BACKUP_DIR"
    fi
    
    BACKUP_NAME=$(basename "$LATEST_BACKUP" .tar.gz)
    log "Найден последний бэкап: $BACKUP_NAME"
else
    BACKUP_NAME="$1"
    LATEST_BACKUP="$BACKUP_DIR/${BACKUP_NAME}.tar.gz"
    
    if [ ! -f "$LATEST_BACKUP" ]; then
        error "Бэкап не найден: $LATEST_BACKUP"
    fi
fi

log "📦 Восстанавливаю из бэкапа: $BACKUP_NAME"

# Останавливаем текущий контейнер
log "🛑 Останавливаю текущий контейнер..."
docker-compose down 2>/dev/null || warning "Контейнер не был запущен"

# Создаем бэкап текущего состояния (на всякий случай)
log "💾 Создаю бэкап текущего состояния..."
CURRENT_BACKUP="rollback_backup_$(date +'%Y%m%d_%H%M%S')"
./backup.sh "$CURRENT_BACKUP"

# Восстанавливаем из бэкапа
log "📥 Восстанавливаю файлы из бэкапа..."
cd "$BACKUP_DIR"
tar -xzf "${BACKUP_NAME}.tar.gz"
cd ..

# Копируем восстановленные файлы
log "📋 Копирую восстановленные файлы..."
cp -r "$BACKUP_DIR/$BACKUP_NAME/data" ./
cp "$BACKUP_DIR/$BACKUP_NAME/.env" ./
cp "$BACKUP_DIR/$BACKUP_NAME/docker-compose.yml" ./

# Очищаем временные файлы
rm -rf "$BACKUP_DIR/$BACKUP_NAME"

# Перезапускаем контейнер
log "🚀 Перезапускаю контейнер..."
docker-compose up -d

# Ждем запуска
log "⏳ Жду запуска..."
sleep 10

# Проверяем статус
if docker-compose ps | grep -q "Up"; then
    success "✅ Откат выполнен успешно!"
    
    log "📋 Статус после отката:"
    docker-compose ps
    
    log "📋 Последние логи:"
    docker-compose logs --tail=10
    
else
    error "❌ Ошибка при откате. Проверьте логи: docker-compose logs"
fi

echo ""
success "🎉 Откат завершен!"
echo "💡 Восстановлен бэкап: $BACKUP_NAME"
echo "💡 Текущее состояние сохранено в: $CURRENT_BACKUP"
