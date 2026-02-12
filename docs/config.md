# Конфигурация проекта Daralla

Переменные окружения и чек-лист для запуска.

---

## Переменные окружения

### Обязательные

| Переменная | Описание |
|------------|----------|
| `TELEGRAM_TOKEN` | Токен бота Telegram (от @BotFather). |
| `YOOKASSA_SHOP_ID` | ID магазина ЮKassa. |
| `YOOKASSA_SECRET_KEY` | Секретный ключ ЮKassa. |
| `ADMIN_ID` или `ADMIN_IDS` | ID администраторов (число или список через запятую). Используется для доступа к админ-API и рассылкам. |

### Веб и webhook

| Переменная | Описание |
|------------|----------|
| `WEBHOOK_URL` | Публичный URL веб-сервера (например `https://daralla.ru`). Нужен для webhook ЮKassa и формирования ссылок на подписку. |
| `WEBAPP_URL` или `WEBSITE_URL` | URL веб-приложения (например `https://daralla.ru/`). |
| `WEBHOOK_PORT` | Порт для HTTP-сервера (по умолчанию 5000). |
| `PORT` | Порт для Quart (по умолчанию 8080), если запускаете отдельно. |

### Опциональные

| Переменная | Описание |
|------------|----------|
| `BOT_USERNAME` | Username бота (по умолчанию `Daralla_bot`). |
| `VPN_BRAND_NAME` | Название бренда в интерфейсе (по умолчанию `Daralla VPN`). |
| `SUBSCRIPTION_URL` | Базовый URL для страницы подписки; если не задан, выводится из `WEBHOOK_URL`. |
| `TELEGRAM_URL` | Ссылка на Telegram (канал/поддержка). |
| `TELEGRAM_CHANNEL_URL` | Ссылка на канал (по умолчанию `https://t.me/DarallaNews`). |
| `IMAGE_MAIN_MENU`, `IMAGE_PAYMENT_SUCCESS`, `IMAGE_PAYMENT_FAILED` | Пути к изображениям для бота. |
| `EVENTS_MODULE_ENABLED` | Включить модуль событий/рефералок: `1`, `true` или `yes`. |
| `EVENTS_SUPPORT_URL` или `SUPPORT_URL` | URL поддержки для событий (по умолчанию `https://t.me/DarallaSupport`). |
| `DARALLA_TEST_DB` | Путь к БД в тестах (например `:memory:` или временный файл). Задаётся до импорта `bot.db`. |

---

## База данных

- **Путь по умолчанию:** `data/daralla.db` (относительно корня проекта).
- **Переопределение в тестах:** задайте `DARALLA_TEST_DB` до импорта модуля `bot.db`.

Инициализация таблиц выполняется при старте приложения (`core/startup.py`).

---

## Модуль событий (Events)

- **Включение:** `EVENTS_MODULE_ENABLED=1` (или `true`/`yes`).
- **Эндпоинты:** под префиксом `/api/events/` (health, список событий, реферальный код, админ CRUD). См. `bot/web/routes/events.py`.
- **БД:** те же `daralla.db`, отдельные таблицы: `events`, `event_referrals`, `event_counted_payments`, `event_rewards_granted`, `user_referral_codes` (создаются в `bot/events/db/migrations.py` при старте).

---

## Чек-лист: поднять проект на новом сервере

1. Установить зависимости: `pip install -r requirements.txt`.
2. Создать `data/` (если нет) — БД создастся при первом запуске.
3. Задать в `.env` или окружении: `TELEGRAM_TOKEN`, `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY`, `ADMIN_ID` (или `ADMIN_IDS`), `WEBHOOK_URL`, при необходимости `WEBAPP_URL`/`WEBSITE_URL`.
4. Добавить серверы X-UI через админку (группы серверов и конфигурация серверов).
5. Запустить бота (например `python -m bot.bot` или через systemd/supervisor).
6. Убедиться, что webhook ЮKassa указывает на `WEBHOOK_URL/webhook/yookassa` и что порт открыт.
