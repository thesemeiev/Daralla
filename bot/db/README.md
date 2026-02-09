# bot/db — единая база daralla.db

Одна SQLite-база `daralla.db` (путь: `DATA_DIR/daralla.db`). Все модули под `bot/db/` работают с этим файлом.

## Таблицы по модулям

| Модуль | Таблицы |
|--------|---------|
| config_db | `config` |
| users_db | `users`, `telegram_links`, `link_telegram_states`, `known_telegram_ids` |
| servers_db | `server_groups`, `servers_config`, `server_load_history` |
| subscriptions_db | `subscriptions`, `subscription_servers` |
| promo_db | `promo_codes`, `promo_code_uses` |
| payments_db | `payments` |
| notifications_db | `sent_notifications`, `notification_metrics`, `notification_settings` |

## Термины

- **user** — запись в таблице `users` (поле `user_id` — строковый идентификатор: `tg_xxx`, `web_xxx` и т.п.; `id` — внутренний INTEGER PK).
- **subscriber_id** в таблице `subscriptions` — это `users.id` (владелец подписки). Слово «подписчик» и «пользователь» обозначают одну и ту же сущность.

## Порядок вызова init (зависимости таблиц)

Функция `init_all_db()` в `bot/db/__init__.py` вызывает перечисленные ниже `init_*` именно в этом порядке — от него зависят внешние ключи между таблицами. При добавлении новых модулей сохраняйте порядок: сначала те, от кого зависят другие.

При инициализации БД модули должны вызываться в таком порядке:

1. `init_config_db()` — config
2. `init_users_db()` — users, telegram_links, link_telegram_states, known_telegram_ids
3. `init_servers_db()` — server_groups, servers_config, server_load_history
4. `init_subscriptions_db()` — subscriptions, subscription_servers (зависят от users.id, server_groups.id)
5. `init_promo_db()` — promo_codes, promo_code_uses (promo_code_uses.user_id → users.user_id)
6. `init_payments_db()` — payments
7. `init_notifications_db()` — sent_notifications, notification_metrics, notification_settings

Зависимости: `subscriptions.subscriber_id` → `users.id`; `subscriptions.group_id` → `server_groups.id`; `subscription_servers.subscription_id` → `subscriptions.id`; `servers_config.group_id` → `server_groups.id`; `telegram_links.user_id` → `users.user_id`.

## Импорты

Импортируйте функции из того модуля, где они определены: `from bot.db.users_db import ...`, `from bot.db.subscriptions_db import ...` и т.д. Либо из пакета: `from bot.db import get_user_by_id, get_subscription_by_token, ...` (все символы реэкспортируются в `bot/db/__init__.py`).
