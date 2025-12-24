#!/bin/bash

# Скрипт для проверки доступности веб-приложения
# Использование: ./check_webapp.sh

echo "🔍 Проверка доступности веб-приложения..."
echo ""

# 1. Проверка Nginx
echo "1️⃣ Проверка Nginx:"
if systemctl is-active --quiet nginx; then
    echo "   ✅ Nginx запущен"
else
    echo "   ❌ Nginx не запущен!"
    echo "   Запустите: sudo systemctl start nginx"
    exit 1
fi

# 2. Проверка Docker контейнера
echo ""
echo "2️⃣ Проверка Docker контейнера:"
if docker ps | grep -q daralla; then
    echo "   ✅ Docker контейнер запущен"
    CONTAINER_NAME=$(docker ps | grep daralla | awk '{print $1}')
    echo "   Контейнер: $CONTAINER_NAME"
else
    echo "   ❌ Docker контейнер не запущен!"
    echo "   Запустите: cd /root/Daralla && docker compose up -d"
    exit 1
fi

# 3. Проверка порта 5000 внутри контейнера
echo ""
echo "3️⃣ Проверка порта 5000 в контейнере:"
if docker exec $CONTAINER_NAME netstat -tuln 2>/dev/null | grep -q ":5000 " || \
   docker exec $CONTAINER_NAME ss -tuln 2>/dev/null | grep -q ":5000 "; then
    echo "   ✅ Порт 5000 слушается в контейнере"
else
    echo "   ⚠️  Порт 5000 не слушается в контейнере (может быть нормально, если используется другой метод)"
fi

# 4. Проверка доступности Flask из хоста
echo ""
echo "4️⃣ Проверка доступности Flask из хоста:"
if curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 http://localhost:5000/webapp/ | grep -q "200\|404\|500"; then
    echo "   ✅ Flask доступен на localhost:5000"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 http://localhost:5000/webapp/)
    echo "   HTTP код: $HTTP_CODE"
else
    echo "   ❌ Flask недоступен на localhost:5000"
    echo "   Проверьте логи контейнера: docker logs $CONTAINER_NAME"
fi

# 5. Проверка Nginx конфигурации
echo ""
echo "5️⃣ Проверка Nginx конфигурации:"
if nginx -t 2>&1 | grep -q "successful"; then
    echo "   ✅ Конфигурация Nginx корректна"
else
    echo "   ❌ Ошибка в конфигурации Nginx!"
    nginx -t
    exit 1
fi

# 6. Проверка проксирования через Nginx
echo ""
echo "6️⃣ Проверка проксирования через Nginx:"
if curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 https://ghosttunnel.space/webapp/ | grep -q "200\|404\|500"; then
    echo "   ✅ Nginx успешно проксирует запросы"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 https://ghosttunnel.space/webapp/)
    echo "   HTTP код: $HTTP_CODE"
else
    echo "   ❌ Nginx не может проксировать запросы"
    echo "   Проверьте логи Nginx: sudo tail -n 50 /var/log/nginx/error.log"
fi

# 7. Проверка логов контейнера
echo ""
echo "7️⃣ Последние строки логов контейнера:"
docker logs --tail 10 $CONTAINER_NAME 2>&1 | tail -5

echo ""
echo "✅ Проверка завершена!"
echo ""
echo "💡 Если Flask недоступен, проверьте:"
echo "   1. Логи контейнера: docker logs $CONTAINER_NAME"
echo "   2. Логи Nginx: sudo tail -n 50 /var/log/nginx/error.log"
echo "   3. Статус контейнера: docker ps -a | grep daralla"

