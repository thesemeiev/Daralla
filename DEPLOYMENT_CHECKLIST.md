# ✅ Чек-лист для деплоя Daralla Bot

## 🔧 **Перед деплоем - проверьте:**

### **1. Переменные окружения в .env:**
```env
# ОБЯЗАТЕЛЬНЫЕ
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
ADMIN_ID=123456789

# ПЛАТЕЖИ (если используете)
YOOKASSA_SHOP_ID=your_shop_id
YOOKASSA_SECRET_KEY=your_secret_key

# СЕРВЕРЫ 3XUI (настройте все используемые)
XUI_HOST_FINLAND=https://finland-1.chechen-community.online
XUI_LOGIN_FINLAND=your_username
XUI_PASSWORD_FINLAND=your_password

XUI_HOST_LATVIA=https://latvia-1.chechen-community.online
XUI_LOGIN_LATVIA=your_username
XUI_PASSWORD_LATVIA=your_password

XUI_HOST_ESTONIA=https://estonia-1.chechen-community.online
XUI_LOGIN_ESTONIA=your_username
XUI_PASSWORD_ESTONIA=your_password
```

### **2. GitHub Secrets (для CI/CD):**
- `SERVER_HOST` - IP или домен сервера
- `SERVER_USER` - SSH пользователь
- `SERVER_SSH_KEY` - приватный SSH ключ
- `SERVER_PORT` - SSH порт (опционально, по умолчанию 22)

### **3. Структура папок на сервере:**
```
/home/your-user/Daralla/
├── .env                    # Ваши настройки
├── data/                   # Базы данных (создастся автоматически)
│   ├── logs/              # Логи
│   ├── vpn_keys.db        # VPN ключи
│   ├── referral_system.db # Реферальная система
│   └── notifications.db   # Уведомления
├── backups/               # Резервные копии
└── ... (остальные файлы)
```

## 🚀 **Процесс деплоя:**

### **Автоматический (рекомендуется):**
1. Настройте GitHub Secrets
2. Создайте .env на сервере
3. Сделайте push в main ветку
4. GitHub Actions автоматически задеплоит

### **Ручной деплой:**
```bash
# На сервере
cd /home/your-user/Daralla
./deploy-server.sh
```

## 🔍 **Проверка после деплоя:**

### **1. Статус контейнера:**
```bash
docker-compose ps
# Должно показать: daralla-bot ... Up
```

### **2. Логи бота:**
```bash
docker-compose logs -f
# Ищите: "=== ИНИЦИАЛИЗАЦИЯ БОТА ЗАВЕРШЕНА ==="
```

### **3. Тест бота:**
- Напишите боту `/start`
- Проверьте команды `/mykey`, `/instruction`
- Проверьте админ-команды (если вы админ)

## 🆘 **Типичные проблемы:**

### **Проблема: "TELEGRAM_TOKEN не найден"**
**Решение:** Проверьте .env файл, переменная должна называться `BOT_TOKEN`

### **Проблема: "Сервер не настроен"**
**Решение:** Добавьте переменные XUI_HOST_*, XUI_LOGIN_*, XUI_PASSWORD_* в .env

### **Проблема: "Ошибка подключения к 3xui"**
**Решение:** Проверьте URL, логин и пароль для серверов

### **Проблема: "База данных заблокирована"**
**Решение:** Остановите старый контейнер: `docker-compose down`

## 🔄 **Откат при проблемах:**

```bash
# На сервере
cd /home/your-user/Daralla
./rollback.sh
```

## 📊 **Мониторинг:**

### **Логи в реальном времени:**
```bash
docker-compose logs -f
```

### **Статус контейнера:**
```bash
docker-compose ps
```

### **Использование ресурсов:**
```bash
docker stats daralla-bot
```

## ✅ **Признаки успешного деплоя:**

1. ✅ Контейнер запущен (`docker-compose ps` показывает "Up")
2. ✅ В логах есть "ИНИЦИАЛИЗАЦИЯ БОТА ЗАВЕРШЕНА"
3. ✅ Бот отвечает на команды
4. ✅ Нет ошибок в логах
5. ✅ Базы данных созданы в папке `data/`

## 🎯 **Рекомендации:**

- **Всегда делайте бэкап** перед деплоем
- **Тестируйте на тестовом сервере** перед продакшеном
- **Мониторьте логи** после деплоя
- **Используйте автоматический деплой** через GitHub Actions
