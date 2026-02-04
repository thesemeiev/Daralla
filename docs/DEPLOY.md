# Деплой: прод и тест

База данных: один файл `data/app.db` (SQLite). Бэкапы в workflow и скрипте `backup.sh` копируют `data/*.db`.

## Схема

| Ветка | Workflow | Куда деплоится |
|-------|----------|----------------|
| **main** | `deploy.yml` | Прод-сервер (secrets: SERVER_HOST, SERVER_USER, …) |
| **test** | `deploy-server2.yml` | Тест-сервер (secrets: TEST_SERVER_HOST, TEST_SERVER_USER, …) |

Пуш в **main** не делайте — прод не изменится. Пуш в **test** запускает деплой только на тест.

---

## Отправить на тест (не трогая прод)

Локально:

```bash
# 1. Закоммитить текущие изменения (если ещё не закоммичены)
git add .
git commit -m "ваше сообщение"

# 2. Создать ветку test от текущего состояния (или переключиться на неё)
git checkout -b test
# если ветка test уже есть и вы хотите её обновить:
# git checkout test
# git merge main   # или merge вашей текущей ветки

# 3. Запушить в ветку test
git push origin test
```

После `git push origin test` в GitHub Actions запустится workflow **"Deploy Daralla Bot to Test Server"**: тесты, линт, затем деплой на тест-сервер. Ветка **main** при этом не меняется.

---

## Что нужно в GitHub

- В **Settings → Secrets and variables → Actions** для тест-деплоя должны быть заданы:
  - `TEST_SERVER_HOST`
  - `TEST_SERVER_USER`
  - `TEST_SERVER_PASSWORD`
  - `TEST_SERVER_PORT` (опционально, по умолчанию 22)
  - `REPO_CLONE_TOKEN` (как и для прода)
  - `WEBHOOK_DOMAIN` (если нужен webhook на тесте)

---

## Когда тест ок — перенести в прод

```bash
git checkout main
git merge test
git push origin main
```

Тогда сработает уже **deploy.yml** и обновится прод-сервер.
