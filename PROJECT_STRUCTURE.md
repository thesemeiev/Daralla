# 📁 Структура проекта Daralla Bot

## 🎯 **Корневая папка:**
```
Daralla/
├── 📁 .github/workflows/          # GitHub Actions CI/CD
│   ├── deploy.yml                 # Основной деплой workflow
│   └── backup.yml                 # Ежедневные бэкапы
├── 📁 bot/                        # Исходный код бота
│   ├── __init__.py
│   ├── bot.py                     # Основной файл бота
│   ├── keys_db.py                 # База данных ключей
│   ├── notifications_db.py        # База уведомлений
│   └── notifications.py           # Система уведомлений
├── 📁 data/                       # Данные (исключены из Git)
│   ├── logs/                      # Логи бота
│   ├── notifications.db           # База уведомлений
│   ├── referral_system.db         # Реферальная система
│   └── vpn_keys.db               # VPN ключи
├── 📄 .gitignore                  # Исключения для Git
├── 📄 .dockerignore               # Исключения для Docker
├── 📄 docker-compose.yml          # Docker Compose конфигурация
├── 📄 Dockerfile                  # Docker образ
├── 📄 requirements.txt            # Python зависимости
├── 📄 README.md                   # Документация
├── 📄 DEPLOYMENT.md               # Инструкция по деплою
├── 📄 env.example                 # Пример переменных окружения
├── 📄 deploy.sh                   # Оригинальный скрипт деплоя
├── 📄 deploy-server.sh            # Улучшенный скрипт деплоя
├── 📄 rollback.sh                 # Скрипт отката
├── 📄 backup.sh                   # Скрипт резервного копирования
└── 📄 setup-server.sh             # Настройка сервера
```

## 🔒 **Файлы, исключенные из Git (.gitignore):**

### **Конфиденциальные данные:**
- `.env` - переменные окружения
- `bot/.env` - локальные настройки

### **Базы данных:**
- `*.db` - все файлы баз данных
- `data/*.db` - базы в папке data
- `data/logs/` - логи

### **Резервные копии:**
- `backups/` - папка с бэкапами
- `*.tar.gz` - архивы бэкапов

### **Системные файлы:**
- `__pycache__/` - кэш Python
- `.vscode/`, `.idea/` - настройки IDE
- `.DS_Store` - системные файлы macOS

## 🐳 **Файлы, исключенные из Docker (.dockerignore):**

### **Не нужны в контейнере:**
- `.git/` - Git репозиторий
- `*.md` - документация (кроме README.md)
- `backups/` - резервные копии
- `data/logs/` - логи
- Скрипты деплоя

## 📊 **Статус файлов в Git:**

### **✅ Добавлены в репозиторий:**
- CI/CD файлы (`.github/workflows/`)
- Скрипты деплоя и управления
- Документация
- Конфигурационные файлы

### **❌ Исключены из репозитория:**
- Базы данных (`data/*.db`)
- Логи (`data/logs/`)
- Переменные окружения (`.env`)
- Резервные копии (`backups/`)

## 🚀 **Рекомендации по использованию:**

### **1. Локальная разработка:**
```bash
# Создайте .env файл из примера
cp env.example .env
# Отредактируйте .env с вашими настройками
```

### **2. Деплой на сервер:**
```bash
# На сервере создайте .env файл
cp env.example .env
# Настройте переменные окружения
```

### **3. Резервное копирование:**
```bash
# Создание бэкапа
./backup.sh
# Восстановление
./rollback.sh
```

## 🔧 **Настройка окружения:**

### **Обязательные переменные в .env:**
```env
BOT_TOKEN=your_telegram_bot_token
ADMIN_ID=your_admin_telegram_id
```

### **Опциональные переменные:**
```env
YOOKASSA_SHOP_ID=your_shop_id
YOOKASSA_SECRET_KEY=your_secret_key
XUI_HOST=https://your-3xui-server.com
XUI_USERNAME=your_username
XUI_PASSWORD=your_password
```

## 📋 **Команды для управления:**

### **Git:**
```bash
git add .
git commit -m "Описание изменений"
git push origin main
```

### **Docker:**
```bash
docker-compose up -d
docker-compose logs -f
docker-compose down
```

### **Скрипты:**
```bash
./deploy-server.sh    # Деплой
./backup.sh          # Бэкап
./rollback.sh        # Откат
```
