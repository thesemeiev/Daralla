# Настройка деплоя на второй сервер

## Шаг 1: Создайте новую ветку

```bash
# Создайте новую ветку для второго сервера
git checkout -b production

# Или используйте другое название, например:
# git checkout -b server2
# git checkout -b staging
```

## Шаг 2: Добавьте секреты в GitHub

Перейдите в настройки репозитория: `Settings` → `Secrets and variables` → `Actions`

Добавьте следующие секреты для второго сервера:

- `SERVER_HOST_2` - IP адрес или домен второго сервера
- `SERVER_USER_2` - имя пользователя для SSH (обычно `root`)
- `SERVER_PASSWORD_2` - пароль для SSH
- `SERVER_PORT_2` - порт SSH (обычно `22`, можно не указывать)

**Важно:** Если вы используете SSH ключи вместо пароля, нужно будет изменить workflow для использования ключей.

## Шаг 3: Настройте workflow (если нужно)

Откройте файл `.github/workflows/deploy-server2.yml` и при необходимости измените:

1. **Название ветки** (строка 5 и 51):
   ```yaml
   branches: [ production ]  # Измените на ваше название
   ```

2. **Название ветки в git checkout** (строка 128):
   ```bash
   sudo git checkout production  # Измените на ваше название
   ```

## Шаг 4: Запушьте код в новую ветку

```bash
# Добавьте все изменения
git add .

# Закоммитьте
git commit -m "Deploy to server 2"

# Запушьте новую ветку
git push origin production
```

## Шаг 5: Проверьте деплой

1. Перейдите в `Actions` в GitHub репозитории
2. Выберите workflow "Deploy Daralla Bot to Server 2"
3. Проверьте статус деплоя

## Альтернатива: Использовать те же секреты

Если вы хотите использовать те же секреты (`SERVER_HOST`, `SERVER_USER`, etc.), но деплоить на другой сервер через другую ветку, измените workflow:

В файле `.github/workflows/deploy-server2.yml` замените:
- `secrets.SERVER_HOST_2` → `secrets.SERVER_HOST`
- `secrets.SERVER_USER_2` → `secrets.SERVER_USER`
- `secrets.SERVER_PASSWORD_2` → `secrets.SERVER_PASSWORD`
- `secrets.SERVER_PORT_2` → `secrets.SERVER_PORT`

## Ручной запуск деплоя

Вы можете запустить деплой вручную:
1. Перейдите в `Actions`
2. Выберите "Deploy Daralla Bot to Server 2"
3. Нажмите "Run workflow"
4. Выберите ветку и нажмите "Run workflow"

## Важные моменты

1. **Базы данных**: При первом деплое на новый сервер базы данных будут пустыми. Если нужно перенести данные, сделайте бэкап с первого сервера и восстановите на втором.

2. **.env файл**: Убедитесь, что на втором сервере есть правильный `.env` файл с нужными переменными окружения.

3. **Порты**: Убедитесь, что порт 5000 свободен на втором сервере.

4. **Docker**: Убедитесь, что Docker и Docker Compose установлены на втором сервере.

## Проверка после деплоя

```bash
# На втором сервере проверьте:
docker-compose ps
docker-compose logs telegram-bot
curl http://localhost:5000/sub/test-token
```

