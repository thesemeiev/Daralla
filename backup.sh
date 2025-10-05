#!/bin/bash

# Скрипт резервного копирования Daralla Bot
# Использование: ./backup.sh [backup_name]

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

# Создаем папку для бэкапов
BACKUP_DIR="./backups"
mkdir -p "$BACKUP_DIR"

# Имя бэкапа
if [ -n "$1" ]; then
    BACKUP_NAME="$1"
else
    BACKUP_NAME="backup_$(date +'%Y%m%d_%H%M%S')"
fi

BACKUP_PATH="$BACKUP_DIR/$BACKUP_NAME"

log "Создаю резервную копию: $BACKUP_NAME"

# Создаем папку для бэкапа
mkdir -p "$BACKUP_PATH"

# Копируем данные
log "Копирую базы данных..."
cp -r ./data "$BACKUP_PATH/" 2>/dev/null || warning "Папка data не найдена"

# Копируем конфигурацию
log "Копирую конфигурацию..."
cp .env "$BACKUP_PATH/" 2>/dev/null || warning "Файл .env не найден"
cp docker-compose.yml "$BACKUP_PATH/" 2>/dev/null || warning "docker-compose.yml не найден"

# Создаем архив
log "Создаю архив..."
cd "$BACKUP_DIR"
tar -czf "${BACKUP_NAME}.tar.gz" "$BACKUP_NAME"
rm -rf "$BACKUP_NAME"

success "Резервная копия создана: $BACKUP_DIR/${BACKUP_NAME}.tar.gz"

# Показываем размер
BACKUP_SIZE=$(du -h "$BACKUP_DIR/${BACKUP_NAME}.tar.gz" | cut -f1)
log "Размер архива: $BACKUP_SIZE"

# Очистка старых бэкапов (оставляем последние 5)
log "Очищаю старые бэкапы..."
cd "$BACKUP_DIR"
ls -t backup_*.tar.gz 2>/dev/null | tail -n +6 | xargs -r rm -f

echo ""
success "Готово!"
echo "💡 Команды:"
echo "   Восстановить: tar -xzf $BACKUP_DIR/${BACKUP_NAME}.tar.gz"
echo "   Список бэкапов: ls -la $BACKUP_DIR/"
