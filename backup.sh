#!/bin/bash

# Создаем папку для бэкапов если её нет
mkdir -p backups

# Имя бэкапа: из аргумента или по умолчанию
BACKUP_NAME="${1:-backup_$(date +%Y%m%d_%H%M%S)}"

# Проверка наличия баз данных
if ! compgen -G "data/*.db" > /dev/null; then
  echo "No .db files found in data/"
  exit 0
fi

# Создаем бэкап всех баз данных
tar -czf "backups/$BACKUP_NAME.tar.gz" data/*.db

# Удаляем старые бэкапы (оставляем только последние 5)
ls -t backups/*.tar.gz 2>/dev/null | tail -n +6 | xargs -r rm -f 2>/dev/null

echo "Backup created: $BACKUP_NAME.tar.gz"
