#!/bin/bash

# Настройка Nginx ПОСЛЕ получения SSL сертификата
# Использование: sudo ./setup_nginx_after_ssl.sh

set -e

DOMAIN="${1:-daralla.ru}"
WEBHOOK_PORT=5000

echo "🚀 Настройка Nginx с SSL для webhook'ов"
echo "📋 Домен: $DOMAIN"
echo "🔌 Порт webhook: $WEBHOOK_PORT"
echo ""

# Проверка прав root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Пожалуйста, запустите скрипт с sudo: sudo ./setup_nginx_after_ssl.sh"
    exit 1
fi

# Проверка наличия SSL сертификата
if [ ! -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    echo "❌ SSL сертификат не найден!"
    echo "   Сначала получите сертификат: sudo certbot certonly --standalone -d $DOMAIN"
    exit 1
fi

echo "✅ SSL сертификат найден"

# 1. Создание директории для acme-challenge (для обновления сертификата)
echo "📁 Создание директории для Let's Encrypt..."
mkdir -p /var/www/html/.well-known/acme-challenge
chown -R www-data:www-data /var/www/html
chmod -R 755 /var/www/html
echo "✅ Директория создана"

# 2. Создание конфигурации Nginx
echo "📝 Создание конфигурации Nginx..."
NGINX_CONFIG="/etc/nginx/sites-available/$DOMAIN"

cat > "$NGINX_CONFIG" << EOF
# Конфигурация для webhook'ов Daralla Bot
# Домен: $DOMAIN

# HTTP сервер - редирект на HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN www.$DOMAIN;

    # Для Let's Encrypt (обновление сертификата)
    location /.well-known/acme-challenge/ {
        root /var/www/html;
        try_files \$uri =404;
    }

    # Редирект всего остального на HTTPS
    location / {
        return 301 https://\$server_name\$request_uri;
    }
}

# HTTPS сервер
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $DOMAIN www.$DOMAIN;
    
    # SSL сертификаты (Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    
    # SSL настройки (современные и безопасные)
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305';
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_stapling on;
    ssl_stapling_verify on;
    
    # Для Let's Encrypt (обновление сертификата)
    location /.well-known/acme-challenge/ {
        root /var/www/html;
        try_files \$uri =404;
    }
    
    # Проксирование на webhook сервер (порт 5000)
    location / {
        proxy_pass http://127.0.0.1:$WEBHOOK_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;
        proxy_set_header X-Forwarded-Port \$server_port;
        
        # Таймауты для долгих запросов
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
        
        # Буферизация
        proxy_buffering off;
        proxy_request_buffering off;
        
        # Обработка ошибок (если бот еще не запущен)
        proxy_next_upstream error timeout invalid_header http_500 http_502 http_503;
        proxy_intercept_errors on;
        error_page 502 503 504 = @fallback;
    }
    
    # Пока контейнер не поднялся — JSON, чтобы фронт и curl не ловили «не JSON» (см. DarallaApiClient.responseJson)
    location @fallback {
        default_type application/json;
        return 503 '{"success":false,"ok":false,"error":"service_starting","message":"Сервис запускается, подождите и обновите страницу."}';
    }
}
EOF

echo "✅ Конфигурация создана: $NGINX_CONFIG"

# 3. Активация конфигурации
echo "🔗 Активация конфигурации..."
if [ -L "/etc/nginx/sites-enabled/$DOMAIN" ]; then
    echo "✅ Симлинк уже существует"
else
    ln -s "$NGINX_CONFIG" "/etc/nginx/sites-enabled/$DOMAIN"
    echo "✅ Симлинк создан"
fi

# Удаление дефолтной конфигурации (если есть)
if [ -L "/etc/nginx/sites-enabled/default" ]; then
    rm /etc/nginx/sites-enabled/default
    echo "✅ Дефолтная конфигурация удалена"
fi

# 4. Проверка конфигурации Nginx
echo "🔍 Проверка конфигурации Nginx..."
if nginx -t; then
    echo "✅ Конфигурация Nginx корректна"
else
    echo "❌ Ошибка в конфигурации Nginx!"
    exit 1
fi

# 5. Открытие портов в firewall (если используется UFW)
if command -v ufw &> /dev/null; then
    echo "🔥 Настройка firewall..."
    ufw allow 80/tcp 2>/dev/null || true
    ufw allow 443/tcp 2>/dev/null || true
    echo "✅ Порты открыты"
fi

# 6. Перезагрузка Nginx
echo "🔄 Перезагрузка Nginx..."
systemctl reload nginx || systemctl restart nginx
echo "✅ Nginx перезагружен"

# 7. Проверка статуса
echo "📊 Статус Nginx:"
systemctl status nginx --no-pager -l | head -n 5

echo ""
echo "✅ Настройка завершена!"
echo ""
echo "📋 Проверьте работу:"
echo "   - HTTP редирект: curl -I http://$DOMAIN"
echo "   - HTTPS: curl -I https://$DOMAIN"
echo "   - Webhook: curl https://$DOMAIN/webhook/yookassa"
echo ""
echo "⚠️  ВАЖНО: Убедитесь, что бот запущен на порту $WEBHOOK_PORT перед тестированием webhook'ов!"

