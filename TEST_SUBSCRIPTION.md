# Тестирование subscription endpoint

## Проблема: SSL/TLS ошибка

Если получаете ошибку SSL, попробуйте:

### 1. Проверьте HTTP версию (без SSL):
```bash
curl -v http://ghosttunnel.space/sub/1b97286f426a4d0687fdc3c3
```

### 2. Игнорируйте SSL ошибки (для тестирования):
```bash
curl -k -v https://ghosttunnel.space/sub/1b97286f426a4d0687fdc3c3
```

### 3. Проверьте логи бота:
```bash
docker-compose logs -f telegram-bot | grep -i "subscription\|vless\|token\|1b97286f426a4d0687fdc3c3"
```

### 4. Проверьте nginx логи:
```bash
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log
```

## Возможные причины 403:

1. **Подписка не активна** - проверьте статус через `/admin_check_subscription`
2. **Подписка истекла** - проверьте expires_at
3. **Сервер недоступен** - проверьте через `/admin_check_servers`
4. **Клиент не найден на X-UI** - проверьте в панели X-UI
5. **Ошибка генерации VLESS ссылок** - проверьте логи

## Проверка SSL сертификата:

```bash
openssl s_client -connect ghosttunnel.space:443 -servername ghosttunnel.space
```

Если сертификат недействителен, нужно:
1. Настроить Let's Encrypt через certbot
2. Или использовать HTTP (не рекомендуется для продакшена)

