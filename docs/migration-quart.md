# Миграция на Quart (ASGI)

Веб-сервер полностью на **Quart** (ASGI) и запускается через **Hypercorn**. Flask удалён.

## Текущее состояние

| Компонент | Файл |
|-----------|------|
| Payment (YooKassa webhook) | `bot/web/routes/payment.py` |
| Subscription (`/sub/<token>`) | `bot/web/routes/subscription.py` |
| API Public (`/api/prices`, `/api/servers`) | `bot/web/routes/api_public.py` |
| API Auth (register, login, verify) | `bot/web/routes/api_auth.py` |
| API User (подписки, платежи, профиль) | `bot/web/routes/api_user.py` |
| Events API (`/api/events/*`) | `bot/web/routes/events.py` |
| Статика (/, webapp) | `bot/web/routes/static.py` |
| API Admin (`/api/admin/*`) | `bot/web/routes/admin_*.py` (check, users, subscriptions, stats, charts, broadcast, servers) |

Все маршруты — async, аутентификация через `bot/handlers/api_support/webhook_auth.py` (`authenticate_request_async`, `check_admin_access_async`).

## Запуск

- **Продакшен**: `python -m bot.bot` — Telegram polling + веб-сервер Quart/Hypercorn на порту `WEBHOOK_PORT` (по умолчанию 5000).
- **Локально только веб**: `python -m bot.web.app_quart` — только Quart (`/health`, статика; полные API требуют `bot_app`).

## Админ-панель

Маршруты `/api/admin/*` в `app_quart.py`: общий модуль `admin_common.py` (CORS, `@admin_route`), blueprints `admin_check`, `admin_users`, `admin_subscriptions`, `admin_stats`, `admin_charts`, `admin_broadcast`, `admin_servers`.

## Безопасность

- Секреты (токены, ключи YooKassa, БД) должны задаваться только через переменные окружения (`.env` / environment в Docker).
- В продакшене не использовать `debug=True`.
- Webhook YooKassa: при необходимости можно добавить проверку IP или подписи согласно документации YooKassa.

## Тесты

- Интеграционные тесты Quart: `tests/integration/test_subscription_quart.py`, `tests/integration/test_quart_routes.py`.
- Запуск: `pytest tests/integration/test_quart_routes.py tests/integration/test_subscription_quart.py -v`.

## См. также

- [migration-py3xui.md](migration-py3xui.md) — миграция на библиотеку py3xui для X-UI API.
