# Миграция на Quart (ASGI)

Веб-сервер переведён с Flask (WSGI) на **Quart** (ASGI) и запускается через **Hypercorn**. Это даёт нативную асинхронность для API и webhook'ов.

## Текущее состояние

| Компонент | Реализация | Файл |
|-----------|------------|------|
| Payment (YooKassa webhook) | Quart (async) | `bot/web/routes/payment_quart.py` |
| Subscription (`/sub/<token>`) | Quart (async) | `bot/web/routes/subscription_quart.py` |
| API Public (`/api/prices`, `/api/servers`) | Quart (async) | `bot/web/routes/api_public_quart.py` |
| API Auth (register, login, verify) | Quart (async) | `bot/web/routes/api_auth_quart.py` |
| API User (подписки, платежи, профиль) | Quart (async) | `bot/web/routes/api_user_quart.py` |
| Статика (/, /index.html, webapp) | Quart (async) | `bot/web/routes/static_quart.py` |
| **API Admin** (`/api/admin/*`) | Quart (async) | `bot/web/routes/admin_*_quart.py` (check, users, subscriptions, stats, charts, broadcast, servers) |
| Events API | Не на Quart | При включённом модуле — только Flask |

## Запуск

- **Продакшен**: `python -m bot.bot` — поднимает Telegram polling и веб-сервер **Quart + Hypercorn** на порту из `WEBHOOK_PORT` (по умолчанию 5000).
- **Порт**: задаётся переменной `WEBHOOK_PORT` в `.env` (см. `.env.example`).
- **Локальная проверка только веб-части**: `python -m bot.web.app_quart` — только Quart, без бота (есть `/health` и статика; полные API требуют `bot_app`).

## Админ-панель

Маршруты `/api/admin/*` работают на Quart и регистрируются в `app_quart.py`: общий модуль `admin_common.py` (CORS, `require_admin`), синие принты `admin_check_quart`, `admin_users_quart`, `admin_subscriptions_quart`, `admin_stats_quart`, `admin_charts_quart`, `admin_broadcast_quart`, `admin_servers_quart`. Flask-версия `api_admin.py` при запуске через Quart не регистрируется (`skip_api_admin=True`).

## Безопасность

- Секреты (токены, ключи YooKassa, БД) должны задаваться только через переменные окружения (`.env` / environment в Docker).
- В продакшене не использовать `debug=True`.
- Webhook YooKassa: при необходимости можно добавить проверку IP или подписи согласно документации YooKassa.

## Тесты

- Интеграционные тесты Quart: `tests/integration/test_subscription_quart.py`, `tests/integration/test_quart_routes.py`.
- Запуск: `pytest tests/integration/test_quart_routes.py tests/integration/test_subscription_quart.py -v`.

## См. также

- [migration-py3xui.md](migration-py3xui.md) — миграция на библиотеку py3xui для X-UI API.
