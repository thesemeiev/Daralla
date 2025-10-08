#!/bin/bash

echo "🔍 Проверка использования места на диске..."
echo "================================================"

# Общее использование диска
echo "📊 Общее использование диска:"
df -h /

echo ""
echo "🐳 Docker использование:"
sudo docker system df

echo ""
echo "📁 Размер логов Docker:"
sudo du -sh /var/lib/docker/containers/*/ 2>/dev/null | head -10

echo ""
echo "🧹 Очистка неиспользуемых ресурсов Docker..."
sudo docker system prune -f
sudo docker volume prune -f
sudo docker image prune -f

echo ""
echo "📊 Использование после очистки:"
df -h /
sudo docker system df

echo ""
echo "✅ Проверка завершена!"
