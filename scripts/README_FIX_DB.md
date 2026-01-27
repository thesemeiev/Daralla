# Как исправить дубли в subscription_servers на действующей БД (сервер)

Если в подписке у пользователей «раздваиваются» серверы (одна и та же локация дважды), в таблице `subscription_servers` могут быть дубли по паре `(subscription_id, server_name)`.

## Вариант 1: Через бота (рекомендуется)

После деплоя обновлённого кода бот при старте сам:

1. Удалит дубли в `subscription_servers`
2. Создаст уникальный индекс `idx_subscription_servers_unique`

Достаточно задеплоить новую версию и перезапустить бота. Миграция выполнится при вызове `init_subscribers_db()`.

---

## Вариант 2: Вручную на сервере (до деплоя или если миграция не сработала)

### 1. Бэкап БД

```bash
cd /path/to/Daralla   # или куда смонтирован проект
cp data/daralla.db data/daralla.db.backup.$(date +%Y%m%d_%H%M)
```

### 2. Остановить бота (чтобы БД не менялась во время правок)

```bash
docker compose stop telegram-bot
# или
docker-compose stop telegram-bot
```

### 3. Выполнить SQL

**Через sqlite3 в контейнере или на хосте:**

```bash
# Путь к БД: обычно ./data/daralla.db относительно проекта
sqlite3 data/daralla.db < scripts/fix_subscription_servers_duplicates.sql
```

**Либо по шагам в интерактиве sqlite3:**

```bash
sqlite3 data/daralla.db
```

В консоли sqlite3:

```sql
-- Проверка дублей (сколько строк будет удалено):
SELECT subscription_id, server_name, COUNT(*) AS cnt
FROM subscription_servers
GROUP BY subscription_id, server_name
HAVING cnt > 1;

-- Очистка и индекс (скопировать из scripts/fix_subscription_servers_duplicates.sql):
DELETE FROM subscription_servers
WHERE EXISTS (
    SELECT 1 FROM subscription_servers s2
    WHERE s2.subscription_id = subscription_servers.subscription_id
      AND s2.server_name = subscription_servers.server_name
      AND s2.id < subscription_servers.id
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_subscription_servers_unique
ON subscription_servers(subscription_id, server_name);

.quit
```

### 4. Запустить бота

```bash
docker compose up -d telegram-bot
```

После этого задеплойте обновлённый код бота — в нём `add_subscription_server` не будет создавать новые дубли.
