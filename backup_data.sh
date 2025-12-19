#!/bin/bash

# Скрипт для создания бэкапа данных реферальной системы
# Использование: ./backup_data.sh

echo "Создание бэкапа данных реферальной системы..."

# Создаем папку для бэкапов если её нет
sudo mkdir -p /root/backups/data

# Создаем бэкап с timestamp
timestamp=$(date +'%Y%m%d_%H%M%S')

if [ -d "data" ] && [ -n "$(ls -A data/*.db 2>/dev/null)" ]; then
    echo "Найдены базы данных для бэкапа:"
    ls -l data/*.db
    
    # Создаем бэкап
    sudo tar -czf "/root/backups/data/backup_${timestamp}.tar.gz" data/*.db
    echo "Бэкап создан: /root/backups/data/backup_${timestamp}.tar.gz"
    
    # Проверяем содержимое бэкапа
    echo "Проверка содержимого бэкапа:"
    sudo tar -tzf "/root/backups/data/backup_${timestamp}.tar.gz"
    
    # Показываем статистику из бэкапа
    echo "Статистика подписок в бэкапе:"
    sudo tar -xzf "/root/backups/data/backup_${timestamp}.tar.gz" -C /tmp/
    if [ -f "/tmp/data/daralla.db" ]; then
        echo "Количество активных подписок:"
        sudo sqlite3 /tmp/data/daralla.db "SELECT COUNT(*) FROM subscriptions WHERE status='active';"
        sudo rm -rf /tmp/data
    fi
    
    # Оставляем только последние 10 бэкапов
    ls -t /root/backups/data/backup_*.tar.gz | tail -n +11 | xargs -r sudo rm -f
    echo "Старые бэкапы удалены (оставлено 10 последних)"
    
else
    echo "Базы данных не найдены для бэкапа"
    exit 1
fi

echo "Бэкап завершен успешно!"
