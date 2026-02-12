# Daralla VPN

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](https://www.docker.com/)

**Платформа управления VPN‑подписками** — Telegram‑бот, веб‑приложение и админ‑панель. Интеграция с X-UI, оплата через YooKassa, единая база данных.

---

## Возможности

- **Telegram Mini App** — покупка, продление и управление подписками без выхода из Telegram
- **Веб‑приложение** — доступ через браузер: регистрация, вход, подписки
- **Админ‑панель** — управление серверами X-UI, подписками, аналитика, промокоды
- **YooKassa** — приём платежей, webhook‑уведомления
- **Мультисерверные подписки** — несколько VPN‑серверов в одной подписке
- **Синхронизация с X-UI** — автоматическая проверка статусов и создание клиентов

## Технологии

| Компонент | Стек |
|-----------|------|
| Бот | Python 3.11, python-telegram-bot |
| Веб/API | Quart (ASGI), Hypercorn |
| База данных | SQLite (aiosqlite) |
| Платежи | YooKassa |
| Инфраструктура | Docker, Docker Compose |

## Быстрый старт

### Требования

- Python 3.11 или Docker
- Telegram Bot Token (от [@BotFather](https://t.me/BotFather))
- Аккаунт YooKassa

### Конфигурация

```bash
cp .env.example .env
```

Заполните `.env`:

| Переменная | Описание |
|------------|----------|
| `TELEGRAM_TOKEN` | Токен Telegram‑бота |
| `ADMIN_ID` | ID администратора(ов) через запятую |
| `YOOKASSA_SHOP_ID` | ID магазина YooKassa |
| `YOOKASSA_SECRET_KEY` | Секретный ключ YooKassa |
| `WEBHOOK_URL` | URL с SSL для webhook (напр. `https://example.com/webhook/yookassa`) |
| `WEBHOOK_PORT` | Порт веб‑сервера (по умолчанию 5000) |
| `WEBSITE_URL` | URL веб‑сайта (опционально) |

Серверы X-UI настраиваются через админ‑панель после запуска.

### Запуск через Docker

```bash
docker compose up -d
```

Веб‑сервер будет доступен на порту **5000** (или на `WEBHOOK_PORT` из `.env`).

### Запуск локально

```bash
pip install -r requirements.txt
python -m bot.bot
```

## Структура проекта

Веб-сервер — только **Quart** (Flask не используется). Все HTTP-маршруты в `bot/web/`: приложение в `app_quart.py`, маршруты в `routes/` (admin_*, api_*, payment, subscription, events, static).

```
Daralla/
├── bot/                    # Ядро бота и бэкенд
│   ├── bot.py              # Точка входа (Telegram + Quart/Hypercorn)
│   ├── core/                # Старт, фоновые задачи, мониторинг
│   ├── db/                  # БД daralla.db — users, subscriptions, servers, payments и др. ([bot/db/README.md](bot/db/README.md))
│   ├── events/              # Модуль событий (рефералы, рейтинги), опционально
│   ├── handlers/            # Команды, колбэки, auth и обработка платежей
│   ├── services/            # Subscription, Server, Sync, X-UI
│   ├── utils/               # UI, helpers, validators
│   └── web/                 # Веб-сервер (Quart): app_quart.py, routes/
├── webapp/                  # Фронтенд (HTML/CSS/JS)
├── docs/                    # Документация (roadmap.md, config.md и др.)
├── tests/
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## Документация

- [docs/config.md](docs/config.md) — переменные окружения, чек-лист запуска на новом сервере, модуль Events.
- [docs/roadmap.md](docs/roadmap.md) — структура проекта и что делать дальше (чистота, именование, тесты).
- [docs/migration-quart.md](docs/migration-quart.md) — веб-сервер на Quart/Hypercorn, маршруты, запуск.
- [docs/migration-py3xui.md](docs/migration-py3xui.md) — интеграция с X-UI через py3xui.

## API

| Endpoint | Метод | Авторизация | Описание |
|----------|-------|-------------|----------|
| `/api/prices` | GET | — | Публичные цены подписок |
| `/api/servers` | GET | TG initData / Bearer | Статус серверов |
| `/api/auth/register` | POST | — | Регистрация |
| `/api/auth/login` | POST | — | Вход |
| `/api/auth/verify` | POST | — | Проверка токена |
| `/webhook/yookassa` | POST | — | Webhook YooKassa |

## CI/CD

- **main** — деплой на production при push
- **test** — деплой на тестовый сервер
- **Ежедневный бэкап** — cron в 03:00 UTC
- **Проверки** — flake8, pytest

## Лицензия

MIT License. См. [LICENSE](LICENSE).
