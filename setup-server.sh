#!/bin/bash

# Скрипт для первоначальной настройки сервера
# Запустите на сервере: bash setup-server.sh

set -e

echo "🚀 Настройка сервера для Daralla Bot..."

# Обновляем систему
echo "📦 Обновляю систему..."
apt update && apt upgrade -y

# Устанавливаем Docker
echo "🐳 Устанавливаю Docker..."
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
usermod -aG docker $USER

# Устанавливаем Docker Compose
echo "🔧 Устанавливаю Docker Compose..."
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Создаем папку для проекта
echo "📁 Создаю папку проекта..."
mkdir -p /home/$USER/Daralla
cd /home/$USER/Daralla

# Клонируем репозиторий
echo "📥 Клонирую репозиторий..."
git clone https://github.com/your-username/Daralla.git .

# Создаем .env файл
echo "⚙️ Создаю .env файл..."
cp env.example .env
echo "📝 Отредактируйте .env файл с вашими настройками!"

# Создаем папки
echo "📂 Создаю необходимые папки..."
mkdir -p data/logs
mkdir -p backups

# Устанавливаем права
echo "🔐 Устанавливаю права..."
chmod +x *.sh

echo ""
echo "✅ Сервер настроен!"
echo "📝 Следующие шаги:"
echo "   1. Отредактируйте .env файл: nano .env"
echo "   2. Настройте GitHub Secrets"
echo "   3. Сделайте push в main ветку для деплоя"
