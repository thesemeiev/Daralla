# 🤖 Daralla Bot

Telegram бот для управления VPN ключами и реферальной системой.

## 🚀 Установка на Linux сервер

### Шаг 1: Подготовка сервера
```bash
# Обновляем систему
sudo apt update && sudo apt upgrade -y

# Устанавливаем Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Устанавливаем Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Перезагружаемся для применения прав
sudo reboot
```

### Шаг 2: Клонирование проекта
```bash
# Клонируем репозиторий
git clone https://github.com/thesemeiev/Daralla.git
cd Daralla
```

### Шаг 3: Настройка бота
```bash
# Запускаем деплой (скрипт сам создаст .env из примера)
chmod +x deploy.sh
./deploy.sh
```

### Шаг 4: Настройка переменных окружения
```bash
# Редактируем .env файл
nano .env
```

**Заполните в .env файле:**
```env
BOT_TOKEN=ваш_токен_от_BotFather
ADMIN_ID=ваш_telegram_id
```

### Шаг 5: Запуск бота
```bash
# Запускаем бота с настройками
./deploy.sh
```

## 🔧 Управление ботом

### Просмотр логов
```bash
docker-compose logs -f
```

### Остановка бота
```bash
docker-compose down
```

### Перезапуск бота
```bash
docker-compose restart
```

### Обновление бота
```bash
./deploy.sh update
```

### Проверка статуса
```bash
docker-compose ps
```

## 📋 Требования

- Ubuntu/Debian Linux сервер
- Docker и Docker Compose
- Git
- Telegram Bot Token (получить у @BotFather)
- Ваш Telegram ID (получить у @userinfobot)

## 🔐 Получение токенов

### Telegram Bot Token:
1. Напишите @BotFather в Telegram
2. Отправьте `/newbot`
3. Придумайте имя и username для бота
4. Скопируйте полученный токен

### Ваш Telegram ID:
1. Напишите @userinfobot в Telegram
2. Скопируйте ваш ID

## 📄 Лицензия

MIT License
