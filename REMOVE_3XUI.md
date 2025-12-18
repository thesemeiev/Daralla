# Удаление 3x-ui и освобождение порта 443

## ⚠️ ВНИМАНИЕ

Удаление 3x-ui приведет к:
- Удалению всех VPN клиентов и конфигураций
- Потере доступа к VPN серверу
- Удалению всех настроек 3x-ui

**Убедитесь, что у вас есть бэкап данных, если они нужны!**

## Шаг 1: Остановите 3x-ui

```bash
# Проверьте, запущен ли 3x-ui
systemctl status x-ui

# Остановите службу
systemctl stop x-ui

# Отключите автозапуск
systemctl disable x-ui
```

## Шаг 2: Удалите 3x-ui

```bash
# Удалите файлы 3x-ui
rm -rf /usr/local/x-ui
rm -rf /etc/x-ui

# Удалите systemd службу
rm -f /etc/systemd/system/x-ui.service
rm -f /usr/lib/systemd/system/x-ui.service

# Перезагрузите systemd
systemctl daemon-reload
```

## Шаг 3: Освободите порт 443

```bash
# Проверьте, что порт 443 свободен
sudo lsof -i :443
sudo ss -tlnp | grep :443

# Если все еще занят, найдите процесс
sudo netstat -tlnp | grep :443
```

## Шаг 4: Удалите связанные процессы (если есть)

```bash
# Найдите процессы, связанные с x-ui или VPN
ps aux | grep x-ui
ps aux | grep xray

# Убейте процессы (если найдены)
sudo pkill -f x-ui
sudo pkill -f xray
```

## Шаг 5: Проверьте firewall правила

```bash
# Проверьте правила iptables
sudo iptables -L -n | grep 443

# Если нужно, удалите правила
sudo iptables -D INPUT -p tcp --dport 443 -j ACCEPT
sudo iptables-save
```

## Шаг 6: Проверьте, что порт свободен

```bash
# Проверьте доступность порта
sudo lsof -i :443
sudo ss -tlnp | grep :443

# Должно быть пусто
```

## Шаг 7: Запустите Nginx

```bash
# Теперь Nginx должен запуститься
sudo systemctl start nginx
sudo systemctl status nginx
```

## Альтернатива: Если 3x-ui установлен через Docker

```bash
# Найдите контейнер
docker ps -a | grep x-ui

# Остановите и удалите контейнер
docker stop <container_id>
docker rm <container_id>

# Удалите образ (если нужно)
docker rmi <image_id>
```

## Альтернатива: Если 3x-ui установлен через скрипт

Если 3x-ui был установлен через официальный скрипт, можно использовать скрипт удаления:

```bash
# Обычно скрипт установки имеет опцию удаления
# Проверьте документацию 3x-ui
```

## После удаления

1. ✅ Порт 443 свободен
2. ✅ Nginx может запуститься на порту 443
3. ✅ SSL сертификат будет работать
4. ✅ Webhook YooKassa будет доступен

## Восстановление (если нужно)

Если нужно восстановить 3x-ui:

```bash
# Установите заново через официальный скрипт
bash <(curl -Ls https://raw.githubusercontent.com/MHSanaei/3x-ui/master/install.sh)
```

## Важно

- **Сделайте бэкап** перед удалением, если данные важны
- **Сообщите пользователям** о временной недоступности VPN
- **Планируйте переустановку** на другой порт, если VPN нужен

