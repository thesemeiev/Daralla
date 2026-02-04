# Архитектура бота Daralla

Документ описывает разделение бота на слои, источник истины по подпискам (Remnawave) и план миграции/рефакторинга от фундамента.

> **Запутались, что старое/новое и что делать дальше?** → см. [STATUS.md](STATUS.md) — там кратко: что уже в порядке, что можно не трогать и один понятный следующий шаг.

---

## 1. Слои (от фундамента к приложению)

```
┌─────────────────────────────────────────────────────────────────┐
│  Application: handlers (Telegram + Web), tasks                   │
├─────────────────────────────────────────────────────────────────┤
│  Domain: accounts, subscriptions (Remnawave), servers, payments  │
├─────────────────────────────────────────────────────────────────┤
│  Foundation: config, db init, paths, logging                     │
└─────────────────────────────────────────────────────────────────┘
```

### 1.1 Foundation (фундамент)

- **Назначение**: конфиг из env, пути к БД/логам, инициализация БД, логирование. Без бизнес-логики.
- **Файлы** (целевые):
  - `bot/config/` — загрузка и валидация env (TELEGRAM_TOKEN, YOOKASSA_*, REMNAWAVE_*, ADMIN_IDS, WEBHOOK_URL, WEBAPP_URL, IMAGE_PATHS, DATA_DIR, логи).
  - `bot/db/` — единая БД `daralla.db`, `init_all_db()`, миграции.
- **Зависимости**: только `os`, `pathlib`, `dotenv`, `logging`; никаких импортов из `services` или `handlers`.

### 1.2 Domain — Accounts

- **Назначение**: аккаунты, идентичности (Telegram, password), привязка к Remnawave (short_uuid, user_uuid), кэш срока подписки.
- **Источник истины по «кто пользователь»**: локальная БД (`accounts`, `identities`, `account_remnawave`, `account_expiry_cache`).
- **Файлы**: `bot/db/accounts_db.py`, миграции в `bot/db/migrations/`.

### 1.3 Domain — Subscriptions (Remnawave)

- **Назначение**: срок подписки, продление, лимиты устройств. Единственный источник истины — Remnawave API.
- **Файлы**:
  - `bot/services/remnawave_service.py` — клиент API (login, get_sub_info, extend, create_user и т.д.).
  - `bot/services/subscription_service.py` — фасад для бота: `get_subscriptions_for_account`, `extend_subscription`, `set_subscription_expiry` (внутри вызывают Remnawave + accounts_db для кэша).
- **Не в этом слое**: создание подписок в локальной БД, синхронизация с X-UI по подпискам — отключены (Remnawave-only).

### 1.4 Domain — Servers

- **Назначение**: группы серверов, конфигурация нод (X-UI), нагрузка, выдача ссылок на подписку. Нужны для админки и (при отсутствии Remnawave) для старой логики — у нас режим Remnawave, поэтому «серверы» в основном для админки и метрик.
- **Файлы**: `bot/db/server_config_db.py`, `bot/services/server_provider.py`, `bot/services/server_manager.py`, `bot/services/xui_service.py`.

### 1.5 Domain — Payments

- **Назначение**: приём платежей (YooKassa), хранение в БД, при успехе — продление/установка срока в Remnawave и уведомление пользователя.
- **Файлы**: `bot/db/payments_db.py`, `bot/handlers/webhooks/payment_processors.py` (логика успешного платежа → Remnawave + accounts).

### 1.6 Application — Handlers

- **Telegram**: команды (`/start`), коллбеки (привязка Telegram), fallback «откройте приложение».
- **Web**: Flask-приложение webhook’ов: YooKassa, API (auth, user, admin, subscription, static). Админка разбита на модули в `bot/handlers/webhooks/routes/admin/`.

### 1.7 Application — Tasks

- Фоновые задачи: уведомления об истечении подписки (из `account_expiry_cache`), очистка старых платежей, снимки нагрузки по серверам (если используется X-UI). Синхронизация «подписки ↔ X-UI» при Remnawave не выполняется.

---

## 2. Remnawave как источник истины

- **Подписки**: срок действия, лимит устройств хранятся только в Remnawave. Локально — только `account_remnawave` (связь account_id ↔ remnawave short_uuid/user_uuid) и кэш срока в `account_expiry_cache` для уведомлений и быстрых проверок.
- **Платежи**: при успешной оплате бот вызывает Remnawave (создание/продление пользователя), обновляет `account_remnawave` и `account_expiry_cache`, затем обновляет статус платежа и шлёт уведомление в Telegram.
- **Уведомления**: список «истекающих скоро» берётся из `account_expiry_cache` (заполняется из Remnawave при оплате и по необходимости).
- **SubscriptionManager / SyncManager**: остаются заглушками для совместимости с кодом, который их запрашивает (например, `get_globals()`). Не создают подписок в БД и не синхронизируют с X-UI в режиме Remnawave.

---

## 3. План миграции и рефакторинга (по фазам)

### Фаза 0 — Текущее состояние (уже сделано)

- Подписки: только Remnawave; `subscribers_db` удалён.
- Админ-API разнесён по модулям в `admin/`.
- Уведомления об истечении — из `account_expiry_cache`.
- Платежи — успех идёт в Remnawave и в accounts_db.

### Фаза 1 — Фундамент: конфиг и точка входа

- Вынести конфиг в отдельный слой:
  - Создать `bot/config/` (или один модуль `bot/config.py`): чтение env, валидация обязательных переменных, константы (ADMIN_IDS, WEBHOOK_URL, WEBAPP_URL, IMAGE_PATHS, пути логов, Remnawave, YooKassa).
  - `bot/bot.py` и остальные модули импортируют конфиг из одного места; не читают `os.getenv` вразнобой.
- Единая точка входа:
  - В `bot/bot.py`: загрузка конфига → создание/инициализация БД → создание сервисов (server_manager, notification_manager, заглушки subscription_manager/sync_manager) → регистрация handlers и tasks. Чёткий порядок инициализации.
- Документировать в этом файле зависимости между слоями (кто кого может импортировать).

### Фаза 2 — Убрать дублирование и «магию»

- Глобальные объекты (`server_manager`, `subscription_manager`, `sync_manager`, `notification_manager`) получать через явный контекст/контейнер (например, один объект `AppContext` или `BotContext`), передаваемый в startup и в webhook_auth, вместо `getattr(bot_module, ...)` по всему коду.
- По возможности сократить использование `sys.modules['bot.bot']` для доступа к глобалам.

### Фаза 3 — Домены: чёткие границы ✅

- **Accounts**: только accounts_db + миграции; Remnawave не импортируется в accounts_db.
- **Subscriptions**: вызов Remnawave и кэш срока в `remnawave_service` + `subscription_service`; добавлена `activate_subscription_after_payment()` — единая точка активации/продления после оплаты.
- **Payments**: payment_processors обновляет payments_db, вызывает только `subscription_service.activate_subscription_after_payment()` и отправляет уведомления; деталей Remnawave API в payment_processors нет.
- **Servers**: server_provider/server_manager — для админки и снимков нагрузки; при Remnawave не участвуют в выдаче подписок.

### Фаза 4 — Очистка заглушек ✅

- При включённом Remnawave (`is_remnawave_configured()`) **не создаются** `SubscriptionManager` и `SyncManager`; в контексте и в модуле `bot.bot` они остаются `None`.
- Startup: `initial_sync` не вызывается при `subscription_manager is None`.
- Tasks: `sync_task_loop` при `sync_manager is None` только ставит паузу, не вызывает `run_sync`.
- Админка `/api/admin/sync-all` при отсутствии `sync_manager` возвращает успех с сообщением «Remnawave mode: sync skipped».
- Режим по умолчанию: Remnawave; без Remnawave заглушки создаются для обратной совместимости.

---

## 4. Зависимости между модулями (правила)

- **Foundation** не импортирует Domain или Application.
- **Domain** не импортирует Application (handlers, webhook_app). Domain может использовать другой Domain (например, subscription_service использует accounts_db и remnawave_service).
- **Application** импортирует Domain и Foundation; получает сервисы через конфиг/контекст, а не через глобальные переменные в случайных модулях.
- Исключение: обратная совместимость во время миграции (например, webhook_auth и payment_processors продолжают получать менеджеры через get_bot_module()) до завершения Фазы 2.

---

## 5. Структура каталогов (целевая)

```
bot/
├── config/           # Фаза 1: конфиг из env
│   └── __init__.py   # или config.py в корне bot/
├── core/             # startup, tasks
├── db/               # единая БД, миграции
├── services/         # domain-сервисы: remnawave, subscription_service, server_*, notification
├── handlers/         # Telegram + Web (webhooks, routes)
├── navigation/
├── utils/
├── bot.py            # точка входа, сборка приложения
└── ...
```

Дальше можно начинать с Фазы 1: вынести конфиг и прописать явный порядок инициализации в `bot.py`.
