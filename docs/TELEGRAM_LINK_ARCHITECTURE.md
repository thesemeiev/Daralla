# Архитектура привязки Telegram к аккаунтам

## Принцип: один аккаунт на один Telegram

- **Аккаунт** — одна запись в `users` (поле `user_id`). Может быть создан из Telegram (TG-first) или с сайта (веб).
- **Связь TG ↔ аккаунт** хранится в `telegram_links` (telegram_id → user_id). Один telegram_id — одна запись.
- При перепривязке TG на другой аккаунт старый аккаунт **не остаётся сиротой**: данные переносятся на новый аккаунт, старый удаляется.

## Ключевые функции (bot/db/subscribers_db.py)

| Функция | Назначение |
|--------|-------------|
| `link_telegram_to_account(telegram_id, target_user_id)` | Единая точка привязки. Если TG был привязан к другому аккаунту — выполняет merge и удаление старого, затем создаёт связь с target. |
| `merge_user_into_target(source_user_id, target_user_id)` | Перенос подписок, платежей, промокодов и т.д. с source на target и удаление записи source из `users`. |
| `get_telegram_chat_id_for_notification(user_id)` | Chat_id для рассылок: сначала `telegram_links`, затем fallback на `users.telegram_id` и числовой user_id. |

## Где вызывается привязка

- **Бот:** `start_handler.py` (при /start link_&lt;state&gt;) и `link_telegram_callback.py` (подтверждение «Да») — вызывают только `link_telegram_to_account(tg_user_id, web_user_id)`.

## Рассылки

- В рассылке (админка и webhook) используется дедупликация по `chat_id`: одному Telegram-чату уходит не более одного сообщения на рассылку.

## Миграция существующих данных

- При старте бота вызывается `migrate_telegram_links()` (идемпотентно): заполняются `telegram_links` и `known_telegram_ids` из текущих данных в `users`. Существующие пользователи и подписки не переносятся и не удаляются.
