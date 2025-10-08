#!/bin/bash

# Скрипт запуска бота с ngrok для webhook'ов

echo "🚀 Запуск бота с ngrok webhook..."

# Проверяем наличие ngrok
if ! command -v ngrok &> /dev/null; then
    echo "❌ ngrok не найден. Устанавливаем..."
    
    # Создаем директорию для ngrok
    sudo mkdir -p /opt/ngrok
    cd /opt/ngrok
    
    # Скачиваем ngrok
    sudo wget -q https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz
    sudo tar -xzf ngrok-v3-stable-linux-amd64.tgz
    sudo rm ngrok-v3-stable-linux-amd64.tgz
    sudo chmod +x ngrok
    sudo ln -sf /opt/ngrok/ngrok /usr/local/bin/ngrok
    
    echo "✅ ngrok установлен"
fi

# Проверяем наличие auth token
if [ -z "$NGROK_AUTH_TOKEN" ]; then
    echo "❌ NGROK_AUTH_TOKEN не установлен"
    echo "Установите переменную NGROK_AUTH_TOKEN в .env файле"
    exit 1
fi

# Настраиваем ngrok
echo "🔧 Настройка ngrok..."
mkdir -p ~/.config/ngrok
cat > ~/.config/ngrok/ngrok.yml << EOF
version: "2"
authtoken: $NGROK_AUTH_TOKEN
tunnels:
  webhook:
    proto: http
    addr: 5000
    bind_tls: true
EOF

# Запускаем ngrok в фоне
echo "🌐 Запуск ngrok туннеля..."
ngrok start webhook --config=~/.config/ngrok/ngrok.yml &
NGROK_PID=$!

# Ждем запуска ngrok
echo "⏳ Ожидание запуска ngrok..."
sleep 10

# Получаем URL
NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | grep -o '"public_url":"[^"]*"' | head -1 | cut -d'"' -f4)

if [ -n "$NGROK_URL" ]; then
    WEBHOOK_URL="${NGROK_URL}/webhook/yookassa"
    echo "✅ Ngrok запущен!"
    echo "📡 URL: $NGROK_URL"
    echo "🔗 Webhook URL: $WEBHOOK_URL"
    
    # Обновляем .env файл
    echo "WEBHOOK_URL=$WEBHOOK_URL" >> .env
    echo "✅ Webhook URL добавлен в .env"
    
    # Настраиваем webhook в YooKassa (если скрипт доступен)
    if [ -f "setup_webhook.py" ]; then
        echo "🔧 Настройка webhook в YooKassa..."
        python3 setup_webhook.py
    fi
    
else
    echo "❌ Не удалось получить ngrok URL"
    kill $NGROK_PID 2>/dev/null
    exit 1
fi

# Запускаем бота
echo "🤖 Запуск бота..."
exec python3 -m bot.bot
