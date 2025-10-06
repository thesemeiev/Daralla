#!/bin/bash

# Создаем папку для бэкапов если её нет
mkdir -p backups

# Имя бэкапа с текущей датой
BACKUP_NAME="backup_$(date +%Y%m%d_%H%M%S)"

# Создаем бэкап всех баз данных
tar -czf "backups/$BACKUP_NAME.tar.gz" data/*.db

# Удаляем старые бэкапы (оставляем только последние 5)
ls -t backups/*.tar.gz | tail -n +6 | xargs rm -f 2>/dev/null

echo "Backup created: $BACKUP_NAME.tar.gz"