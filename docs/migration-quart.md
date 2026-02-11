# Миграция на Quart (ASGI)

Веб-сервер полностью на **Quart** (ASGI) и запускается через **Hypercorn**. Flask удалён.

## Текущее состояние

| Компонент | Файл |
|-----------|------|
| Payment (YooKassa webhook) | `bot/web/routes/payment_quart.py` |
| Subscription (`/sub/<token>`) | `bot/web/routes/subscription_quart.py` |
| API Public (`/api/prices`, `/api/servers`) | `bot/web/routes/api_public_quart.py` |
| API Auth (register, login, verify) | `bot/web/routes/api_auth_quart.py` |
| API User (подписки, платежи, профиль) | `bot/web/routes/api_user_quart.py` |
| Events API (`/api/events/*`) | `bot/web/routes/events_quart.py` |
| Статика (/, webapp) | `bot/web/routes/static_quart.py` |
| API Admin (`/api/admin/*`) | `bot/web/routes/admin_*_quart.py` (check, users, subscriptions, stats, charts, broadcast, servers) |

Все маршруты — async, аутентификация через `bot/handlers/webhooks/webhook_auth.py` (`authenticate_request_async`, `check_admin_access_async`).

## Запуск

- **Продакшен**: `python -m bot.bot` — Telegram polling + веб-сервер Quart/Hypercorn на порту `WEBHOOK_PORT` (по умолчанию 5000).
- **Локально только веб**: `python -m bot.web.app_quart` — только Quart (`/health`, статика; полные API требуют `bot_app`).

## Админ-панель

Маршруты `/api/admin/*` в `app_quart.py`: общий модуль `admin_common.py` (CORS, `require_admin`), blueprints `admin_check_quart`, `admin_users_quart`, `admin_subscriptions_quart`, `admin_stats_quart`, `admin_charts_quart`, `admin_broadcast_quart`, `admin_servers_quart`.

## Безопасность

- Секреты (токены, ключи YooKassa, БД) должны задаваться только через переменные окружения (`.env` / environment в Docker).
- В продакшене не использовать `debug=True`.
- Webhook YooKassa: при необходимости можно добавить проверку IP или подписи согласно документации YooKassa.

## Тесты

- Интеграционные тесты Quart: `tests/integration/test_subscription_quart.py`, `tests/integration/test_quart_routes.py`.
- Запуск: `pytest tests/integration/test_quart_routes.py tests/integration/test_subscription_quart.py -v`.

## См. также

- [migration-py3xui.md](migration-py3xui.md) — миграция на библиотеку py3xui для X-UI API.
