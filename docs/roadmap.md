# Структура проекта и дорожная карта

Краткий обзор текущей структуры и шаги к чистой, предсказуемой кодовой базе.

---

## Текущая структура (после миграции на Quart)

```
Daralla/
├── bot/                          # Ядро приложения
│   ├── bot.py                    # Точка входа: Telegram + Quart/Hypercorn
│   ├── core/                     # Старт, фоновые задачи, мониторинг
│   │   ├── startup.py            # on_startup: БД, менеджеры, events-таблицы
│   │   └── tasks.py              # Синхронизация подписок, нагрузка серверов
│   ├── db/                       # Единая БД (daralla.db): пользователи, подписки, серверы, платежи
│   ├── events/                   # Модуль событий (рефералы, рейтинги) — опционально (EVENTS_MODULE_ENABLED)
│   │   ├── db/                   # Таблицы событий в той же daralla.db
│   │   ├── services/
│   │   ├── config.py
│   │   └── payment_hook.py        # Хук успешной оплаты
│   ├── handlers/
│   │   ├── commands/             # /start и т.д.
│   │   ├── callbacks/            # link_telegram и т.д.
│   │   ├── api_support/           # Поддержка веб-API: auth и обработка платежей
│   │   │   ├── webhook_auth.py   # authenticate_request_async, check_admin_access_async
│   │   │   └── payment_processors.py  # Обработка webhook'ов YooKassa
│   │   └── utils/                # error_handler
│   ├── navigation/               # Состояния меню
│   ├── services/                 # Бизнес-логика: подписки, серверы, X-UI, синхронизация
│   ├── utils/                    # UI, helpers, validators
│   ├── prices_config.py
│   └── web/                      # Веб-сервер (Quart)
│       ├── app_quart.py          # Создание приложения, регистрация blueprints
│       └── routes/               # Все HTTP-маршруты (admin_*.py, api_*.py, payment, subscription, events, static)
├── webapp/                       # Фронтенд (HTML/CSS/JS)
├── tests/
├── docs/
└── ...
```

**Идея разделения:**

- **bot/** — всё, что относится к боту и бэкенду: БД, сервисы, обработчики Telegram, логика оплаты.
- **bot/web/** — только Quart-приложение и маршруты; маршруты вызывают сервисы и `api_support` (auth).
- **bot/handlers/api_support/** — общая логика для веб-API: аутентификация (webhook_auth) и обработка платежей YooKassa (payment_processors).

---

## Что уже сделано

1. **Quart вместо Flask** — весь HTTP API на Quart, Flask удалён из кода и из `requirements.txt`.
2. **Один веб-сервер** — только `create_quart_app()` в `bot/web/app_quart.py`; маршруты только в `bot/web/routes/`.
3. **Events как часть приложения** — API событий в `routes/events.py`, без отдельного Flask-модуля.
4. **Одна БД** — `daralla.db`; модуль events использует `bot.db.DB_PATH` и свои таблицы (инициализация в `core/startup.py`).

---

## Что делать дальше (по приоритету)

### 1. Ничего не ломая (можно делать сразу)

- **Обновить README** — в разделе «Структура проекта» указать `bot/web/` и что веб — только Quart (без упоминания Flask).
- **Проверить тесты** — `pytest tests/ -v`; при необходимости поправить импорты/моки под текущие имена (уже используются `check_admin_access_async` и т.п.).

### 2. Именование и порядок (по желанию)

- **Суффикс `_quart`** — сейчас все маршруты в `bot/web/routes/` называются `*_quart.py`. Так как Flask больше нет, суффикс можно со временем убрать (переименовать в `api_user.py`, `payment.py` и т.д.) для краткости. Не обязательно, но упрощает названия.
- **Папка `handlers/api_support`** — переименована из `webhooks`; содержит общую логику для веб-API (auth) и обработку платежей YooKassa. При желании можно вынести `webhook_auth.py` в `bot/auth/` или `bot/web/auth.py` — по необходимости.

### 3. Консистентность кода

- **CORS и админ-роуты** — CORS вынесен в `admin_common.py` (единый `CORS_HEADERS` и `_cors_headers()`); все админ-маршруты, включая broadcast, используют декоратор `@admin_route` (OPTIONS + `require_admin` + общий try/except с 500). User API и events используют тот же `CORS_HEADERS` из `admin_common`.
- **X-UI слой (X3)** — зафиксирован единый контракт:
   - информационные методы (`client_exists`, `get_client_expiry_time`, `get_client_info`, `list` и т.п.) возвращают значения/`None` и не бросают исключения в «нормальных» ситуациях (например, клиент не найден);
   - методы, меняющие состояние (`addClient`, `extendClient`, `setClientExpiry`, `updateClientLimitIp`, `updateClientName`, `deleteClient`) сигнализируют об успехе отсутствием исключения; там, где важно различать «нашли/не нашли» (`setClientExpiry`, `updateClientLimitIp`, `deleteClient`), возвращается `bool` (`True` — изменение выполнено, `False` — клиент не найден/не изменён);
   - код, который раньше проверял `response.status_code` / `response.json()`, упрощён и полагается на этот контракт.

### 4. Документация и конфиг

- **Переменные окружения и чек-лист** — см. `docs/config.md`: полный список env (`TELEGRAM_TOKEN`, `ADMIN_ID(S)`, `YOOKASSA_*`, `WEBHOOK_URL`, `WEBSITE_URL`, `EVENTS_MODULE_ENABLED`, `DARALLA_TEST_DB` и др.) и краткий чек-лист «как поднять проект на новом сервере».
- **Events** — в `docs/config.md` описано: включение через `EVENTS_MODULE_ENABLED`, эндпоинты `/api/events/*`, таблицы в БД (`bot/events/db/migrations.py`).

### 5. Дальнейшие улучшения (когда будет время)

- **Типизация** — по мере правок подключать type hints для публичных функций и сервисов.
- **Логирование** — единый формат логов (например, JSON для продакшена) и уровень по окружению.
- **Тесты** — добавлять интеграционные тесты на критические сценарии (оплата, создание подписки, админка) поверх Quart-клиента.

---

## Куда двигаться по смыслу

- **Сейчас проект уже структурирован:** один веб-стек (Quart), одна БД, чёткое место для маршрутов (`bot/web/routes/`) и для логики (сервисы, handlers).
- **Следующий шаг** — не перекладывать всё заново, а:
  1. Зафиксировать текущую структуру в README и в этом `roadmap.md`.
  2. Постепенно уменьшать дублирование и держать имена понятными (CORS и админ-роуты уже унифицированы; `handlers/webhooks` переименован в `api_support`).
  3. Держать в актуальном состоянии список env-переменных и опцию Events.

Так вы сохраняете «хороший, структурированный и чистый» проект без больших рисков и без лишнего рефакторинга.
