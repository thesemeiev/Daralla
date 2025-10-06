#!/bin/bash

# Скрипт для исправления прав доступа к базам данных
echo "🔧 Исправляю права доступа к базам данных..."

# Переходим в папку с ботом
cd /root/Daralla || { echo "❌ Папка /root/Daralla не найдена!"; exit 1; }

# Останавливаем бота
echo "🛑 Останавливаю бота..."
sudo docker-compose down

# Создаем папку data если её нет
sudo mkdir -p data

# Создаем файлы БД если их нет
sudo touch data/vpn_keys.db data/referral_system.db data/notifications.db

# Устанавливаем правильные права
echo "📝 Устанавливаю права доступа..."
sudo chown -R 1000:1000 data/
sudo chmod -R 666 data/*.db
sudo chmod 755 data/

# Проверяем права
echo "✅ Проверяю права доступа:"
ls -la data/

# Запускаем бота
echo "🚀 Запускаю бота..."
sudo docker-compose up -d

# Проверяем статус
echo "📊 Статус бота:"
sudo docker-compose ps

echo "🎉 Исправление прав завершено!"

