-- Очистка дублей в subscription_servers и создание уникального индекса
-- Выполнять на сервере вручную, если миграция в боте не сработала или нужно почистить БД до деплоя.
--
-- 1. Обязательно сделайте бэкап БД:
--    cp data/daralla.db data/daralla.db.backup.$(date +%Y%m%d)
--
-- 2. Выполните скрипт (см. README_FIX_DB.md)

-- Удалить дубли: оставить по одной строке на пару (subscription_id, server_name), с минимальным id
DELETE FROM subscription_servers
WHERE EXISTS (
    SELECT 1 FROM subscription_servers s2
    WHERE s2.subscription_id = subscription_servers.subscription_id
      AND s2.server_name = subscription_servers.server_name
      AND s2.id < subscription_servers.id
);

-- Создать уникальный индекс, чтобы дубли не появлялись снова
CREATE UNIQUE INDEX IF NOT EXISTS idx_subscription_servers_unique
ON subscription_servers(subscription_id, server_name);
