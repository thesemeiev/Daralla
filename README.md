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
| Веб/API | Flask |
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
| `WEBSITE_URL` | URL веб‑сайта (опционально) |

Серверы X-UI настраиваются через админ‑панель после запуска.

### Запуск через Docker

```bash
docker compose up -d
```

Приложение будет доступно на порту **5000**.

### Запуск локально

```bash
pip install -r requirements.txt
python -m bot.bot
```

## Структура проекта

```
Daralla/
├── bot/                    # Ядро бота
│   ├── bot.py              # Точка входа
│   ├── core/               # Старт, мониторинг
│   ├── db/                 # Работа с БД (daralla.db). Модули: config, users, servers, subscriptions, promo, payments, notifications — см. [bot/db/README.md](bot/db/README.md)
│   ├── handlers/           # Команды, webhooks, API
│   ├── services/           # Subscription, Server, Sync
│   └── utils/              # UI, helpers, validators
├── webapp/                 # Веб‑приложение (HTML/CSS/JS)
├── images/                 # Изображения для меню
├── data/                   # БД, логи (создаётся при запуске)
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

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
