# 🤖 Daralla Bot

Telegram бот для управления VPN ключами и реферальной системой.

## 🚀 Быстрый старт

1. **Клонируйте репозиторий:**
   ```bash
   git clone https://github.com/yourusername/daralla-bot.git
   cd daralla-bot
   ```

2. **Создайте файл `.env`:**
   ```bash
   cp env.example .env
   # Отредактируйте .env файл с вашими настройками
   ```

3. **Запустите бота:**
   ```bash
   chmod +x deploy.sh
   ./deploy.sh
   ```

## 🔧 Управление

### Обновление бота
```bash
./deploy.sh update
```

### Просмотр логов
```bash
docker-compose logs -f
```

### Остановка
```bash
docker-compose down
```

## 📋 Требования

- Docker и Docker Compose
- Git
- Telegram Bot Token

## 📄 Лицензия

MIT License
