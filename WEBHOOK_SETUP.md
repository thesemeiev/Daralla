# 🔗 Настройка Webhook'ов с ngrok

## 📋 Что нужно сделать:

### 1. **Получить ngrok Auth Token:**
1. Зайдите на [https://ngrok.com/signup](https://ngrok.com/signup)
2. Зарегистрируйтесь (бесплатно)
3. Войдите в [Dashboard](https://dashboard.ngrok.com/get-started/your-authtoken)
4. Скопируйте ваш **Auth Token**

### 2. **Добавить токен в GitHub Secrets:**
1. Зайдите в ваш репозиторий на GitHub
2. Перейдите в **Settings** → **Secrets and variables** → **Actions**
3. Нажмите **New repository secret**
4. Название: `NGROK_AUTH_TOKEN`
5. Значение: ваш токен из ngrok

### 3. **Деплой:**
Просто сделайте коммит и пуш - все настроится автоматически!

```bash
git add .
git commit -m "Add ngrok webhook support"
git push origin main
```

## 🚀 Что происходит при деплое:

1. **Устанавливается ngrok** на сервер
2. **Запускается туннель** на порт 5000
3. **Получается публичный URL** (например: `https://abc123.ngrok.io`)
4. **Настраивается webhook** в YooKassa автоматически
5. **Запускается бот** с поддержкой webhook'ов

## 📡 Webhook URL:

После деплоя webhook URL будет:
```
https://your-ngrok-url.ngrok.io/webhook/yookassa
```

## 🔧 Ручная настройка (если нужно):

Если автоматическая настройка не сработала:

1. **Получите ngrok URL:**
```bash
curl http://localhost:4040/api/tunnels
```

2. **Настройте webhook в YooKassa:**
   - Зайдите в [личный кабинет YooKassa](https://yookassa.ru/my)
   - **Настройки** → **Webhook**
   - **Добавить webhook**
   - URL: `https://your-ngrok-url.ngrok.io/webhook/yookassa`
   - События: `payment.succeeded`, `payment.canceled`, `payment.refunded`

## ✅ Проверка работы:

1. **Проверьте логи деплоя** в GitHub Actions
2. **Сделайте тестовый платеж** в боте
3. **Проверьте логи бота** - должны появиться webhook'и

## 🆘 Решение проблем:

### Ngrok не запускается:
- Проверьте `NGROK_AUTH_TOKEN` в GitHub Secrets
- Убедитесь, что токен правильный

### Webhook не работает:
- Проверьте URL в YooKassa
- Убедитесь, что ngrok туннель активен
- Проверьте логи бота

### Бот не получает уведомления:
- Проверьте, что webhook настроен в YooKassa
- Убедитесь, что события выбраны правильно
- Проверьте логи ngrok: `http://localhost:4040`
