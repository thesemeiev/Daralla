# Пошаговое исправление nginx

## Проблема
Файл конфигурации называется `your-domain.com`, но должен быть `ghosttunnel.space`.

## Шаги исправления:

### 1. Переименуйте файл конфигурации:

```bash
sudo mv /etc/nginx/sites-available/your-domain.com /etc/nginx/sites-available/ghosttunnel.space
```

### 2. Отредактируйте файл (если нужно):

```bash
sudo nano /etc/nginx/sites-available/ghosttunnel.space
```

Убедитесь, что содержимое:
```nginx
server {
    listen 80;
    server_name ghosttunnel.space www.ghosttunnel.space;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Таймауты
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

### 3. Удалите старый симлинк (если есть):

```bash
sudo rm /etc/nginx/sites-enabled/your-domain.com
```

### 4. Создайте новый симлинк:

```bash
sudo ln -s /etc/nginx/sites-available/ghosttunnel.space /etc/nginx/sites-enabled/
```

### 5. Проверьте конфигурацию:

```bash
sudo nginx -t
```

Должно быть: `syntax is ok` и `test is successful`

### 6. Перезагрузите nginx:

```bash
sudo systemctl reload nginx
```

### 7. Проверьте, что Flask работает:

```bash
# Проверьте, что контейнер запущен
docker-compose ps

# Проверьте логи
docker-compose logs telegram-bot | grep "Webhook сервер"

# Проверьте локально
curl http://localhost:5000/sub/1b97286f426a4d0687fdc3c3
```

### 8. Проверьте, что nginx проксирует запросы:

```bash
# Проверьте логи nginx
sudo tail -f /var/log/nginx/access.log

# В другом терминале сделайте запрос:
curl http://ghosttunnel.space/sub/1b97286f426a4d0687fdc3c3
```

### 9. Если все еще 404, проверьте:

```bash
# Проверьте, какие конфигурации активны
ls -la /etc/nginx/sites-enabled/

# Проверьте, нет ли конфликтующих конфигураций
sudo grep -r "ghosttunnel.space" /etc/nginx/sites-available/
sudo grep -r "ghosttunnel.space" /etc/nginx/sites-enabled/

# Проверьте default конфигурацию (может перехватывать запросы)
sudo cat /etc/nginx/sites-available/default
```

### 10. Если default конфигурация мешает:

```bash
# Отключите default
sudo rm /etc/nginx/sites-enabled/default

# Перезагрузите nginx
sudo systemctl reload nginx
```

## Проверка после исправления:

После выполнения всех шагов, проверьте:

```bash
# С сервера
curl -v http://ghosttunnel.space/sub/1b97286f426a4d0687fdc3c3

# Или из PowerShell (Windows)
Invoke-WebRequest -Uri "http://ghosttunnel.space/sub/1b97286f426a4d0687fdc3c3" -UseBasicParsing
```

## Возможные проблемы:

1. **Порт 5000 не доступен** - проверьте `docker-compose ps` и логи
2. **Firewall блокирует** - проверьте `sudo ufw status`
3. **Docker сеть** - убедитесь, что порт проброшен: `docker port daralla-bot`
4. **Конфликт конфигураций** - проверьте все файлы в `sites-enabled/`

