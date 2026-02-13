# Daralla VPN

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](https://www.docker.com/)

**Платформа управления VPN‑подписками** — Telegram‑бот, веб‑приложение и админ‑панель. Интеграция с X-UI, оплата через YooKassa, единая база данных.

---

## Возможности

- **Telegram Mini App** — покупка, продление и управление подписками без выхода из Telegram
- **Веб‑приложение** — доступ через браузер: регистрация, вход, подписки
- **Админ‑панель** — управление серверами X-UI, подписками, аналитика
- **YooKassa** — приём платежей, webhook‑уведомления
- **Мультисерверные подписки** — несколько VPN‑серверов в одной подписке
- **Синхронизация с X-UI** — автоматическая проверка статусов и создание клиентов

## Технологии

| Компонент   | Стек                          |
|------------|-------------------------------|
| Бот        | Python 3.11, python-telegram-bot |
| Веб/API    | Quart (ASGI), Hypercorn       |
| База данных | SQLite (aiosqlite)          |
| Платежи    | YooKassa                      |
| Инфраструктура | Docker, Docker Compose    |

## Быстрый старт

### Требования

- Python 3.11 или Docker
- Токен бота Telegram ([@BotFather](https://t.me/BotFather))
- Аккаунт YooKassa

### Конфигурация

```bash
cp .env.example .env
```

Заполните `.env` (основные переменные):

| Переменная | Описание |
|------------|----------|
| `TELEGRAM_TOKEN` | Токен Telegram‑бота |
| `ADMIN_ID` | ID администратора(ов) через запятую |
| `YOOKASSA_SHOP_ID` | ID магазина YooKassa |
| `YOOKASSA_SECRET_KEY` | Секретный ключ YooKassa |
| `WEBHOOK_URL` | URL с SSL для webhook (например `https://example.com/webhook/yookassa`) |
| `WEBHOOK_PORT` | Порт веб‑сервера (по умолчанию 5000) |
| `WEBAPP_URL` | URL мини‑приложения для кнопок «Открыть в приложении» |
| `WEBSITE_URL` | URL веб‑сайта (опционально) |

Серверы X-UI настраиваются через админ‑панель после запуска. Полный список переменных — в `.env.example`.

### Запуск через Docker

```bash
docker compose up -d
```

Веб‑сервер будет доступен на порту **5000** (или на `WEBHOOK_PORT` из `.env`).

### Запуск локально

```bash
pip install -r requirements.txt
# Из корня проекта (каталог Daralla):
python bot/bot.py
```

На Windows при необходимости задайте `PYTHONPATH` в корень проекта: `set PYTHONPATH=.`  
На Linux/macOS: `export PYTHONPATH=.`

## Структура проекта

Веб‑сервер — **Quart**. HTTP‑маршруты в `bot/web/`: приложение в `app_quart.py`, маршруты в `routes/` (admin_*, api_*, payment, subscription, events, static).

```
Daralla/
├── bot/                    # Ядро бота и бэкенд
│   ├── bot.py              # Точка входа (Telegram + Quart/Hypercorn)
│   ├── core/               # Старт, фоновые задачи
│   ├── db/                 # Единая БД daralla.db (users, subscriptions, servers, payments и др.)
│   ├── events/             # Модуль событий (рефералы, рейтинги), опционально
│   ├── handlers/           # Команды, колбэки, auth, обработка платежей
│   ├── services/           # Subscription, Server, Sync, X-UI
│   ├── utils/              # UI, helpers, validators
│   └── web/                # Веб‑сервер Quart: app_quart.py, routes/
├── webapp/                 # Фронтенд (HTML/CSS/JS), PWA
├── tests/                  # Unit и интеграционные тесты
├── images/                 # Изображения для бота (меню, уведомления)
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## Архитектура: Telegram vs Web

Один SPA (`webapp/`) обслуживает и Telegram Mini App, и веб‑доступ через браузер. Режим определяется автоматически.

| Режим | Определение | Авторизация |
|-------|-------------|-------------|
| **Telegram** | Есть `tg.initData` (приложение открыто из Telegram) | `initData` передаётся в каждом запросе к API |
| **Web** | Нет `tg.initData` (прямой заход на сайт) | Логин/пароль → Bearer‑токен в заголовках |

Оба режима используют одни и те же API и единый бэкенд (Quart). Данные пользователя — общие.

### Внешние ресурсы и блокировки

| Ресурс | Где используется | Обработка при недоступности |
|--------|------------------|-----------------------------|
| `telegram.org/js/telegram-web-app.js` | Инициализация Mini App | Таймаут 400 мс, заглушка `TG_STUB` — страница открывается без Telegram API |
| `cdn.jsdelivr.net` (Chart.js) | Графики в админ‑панели | Lazy load при переходе в раздел — не блокирует загрузку страницы; при ошибке показывается fallback |

Лендинг, вход и основные разделы работают без VPN. Графики админки подгружают Chart.js по запросу; при блокировке CDN выводится сообщение: «Графики недоступны. Проверьте сеть или попробуйте с VPN».

## API

| Endpoint | Метод | Авторизация | Описание |
|----------|-------|-------------|----------|
| `/api/prices` | GET | — | Публичные цены подписок |
| `/api/servers` | GET | TG initData / Bearer | Статус серверов |
| `/api/auth/register` | POST | — | Регистрация |
| `/api/auth/login` | POST | — | Вход |
| `/api/auth/verify` | POST | — | Проверка токена |
| `/health` | GET | — | Проверка доступности сервиса |
| `/webhook/yookassa` | POST | — | Webhook YooKassa |

## CI/CD

- **main** — деплой на production при push
- **test** — деплой на тестовый сервер (workflow `deploy-server2.yml`)
- **Ежедневный бэкап** — workflow `backup.yml`, 03:00 UTC
- **Проверки** — flake8, pytest перед деплоем

## Лицензия

MIT License. См. [LICENSE](LICENSE).
