<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Telegram-Bot_API-26A5E4?style=for-the-badge&logo=telegram&logoColor=white" alt="Telegram">
  <img src="https://img.shields.io/badge/Quart-ASGI-000000?style=for-the-badge&logo=quart&logoColor=white" alt="Quart">
  <img src="https://img.shields.io/badge/SQLite-aiosqlite-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker">
</p>

# Daralla VPN

Платформа для продажи и управления VPN-подписками через **Telegram Mini App**, **веб-клиент** и **админ-панель**. Полная автоматизация: от оплаты до создания клиентов на серверах [3x-ui](https://github.com/MHSanaei/3x-ui).

---

## Возможности

### Клиентская часть

- **Telegram Mini App** — покупка, продление и управление подписками прямо в Telegram
- **Веб-клиент** — лендинг с авторизацией по логину/паролю, полнофункциональный интерфейс
- **Два шлюза оплаты** — YooKassa (карты, СБП) и CryptoCloud (USDT, BTC, ETH, TON, SOL и др.)
- **Подписочные ссылки** — `/sub/{token}` для подключения через любой VLESS-клиент

### Серверная часть

- **Мультисервер** — группы серверов по локациям, одна подписка = доступ ко всем серверам группы
- **Автоматическая синхронизация** — создание, обновление и удаление клиентов на панелях 3x-ui
- **Балансировка** — автоматический выбор наименее загруженной группы серверов
- **Мониторинг нагрузки** — сбор статистики онлайн-клиентов по каждому серверу

### Уведомления

- **Гибкие правила** — настройка через админ-панель: тип события, время срабатывания, шаблон сообщения
- **Повторная отправка** — настраиваемый интервал и максимум повторов
- **Типы событий** — предупреждение об истечении подписки, напоминание пользователям без подписки

### Админ-панель

- **Дашборд** — карточки MRR, активных подписок, пользователей и конверсии; график выручки за 30 дней с разбивкой по платёжным шлюзам; мониторинг нагрузки серверов
- **Пользователи** — поиск, просмотр деталей, привязка подписок, удаление
- **Подписки** — фильтры по статусу, ручная синхронизация с серверами, изменение параметров
- **Серверы** — CRUD групп и серверов, настройка подключений к 3x-ui
- **Рассылка** — отправка сообщений всем пользователям с rate-limiting
- **Управление уведомлениями** — создание правил, тестовая отправка, превью сообщений

### Модуль событий (опционально)

- **Реферальные конкурсы** — создание событий с датами и наградами
- **Уникальные коды** — автогенерация реферальных кодов для каждого участника
- **Лидерборд** — рейтинг по количеству успешных приглашений
- **Автовыдача наград** — дни подписки за достижения в конкурсе

---

## Архитектура

```
┌──────────────────────────────────────────────────────────────┐
│                        Пользователь                          │
└──────────────────────────────────────────────────────────────┘
         │ Web (логин/пароль)                │ Telegram
         ▼                                   ▼
┌─────────────────────┐           ┌─────────────────────────┐
│    daralla.ru       │           │    Telegram Mini App    │
│    Веб-клиент       │           │    initData auth        │
└─────────┬───────────┘           └────────────┬────────────┘
          └────────────────┬───────────────────┘
                           ▼
              ┌──────────────────────┐
              │   Quart Backend      │
              │   API + Webhooks     │
              ├──────────────────────┤
              │ /api/user/*          │
              │ /api/admin/*         │
              │ /webhook/yookassa    │
              │ /webhook/cryptocloud │
              └──────────┬───────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
   ┌────────────┐ ┌────────────┐ ┌────────────┐
   │  SQLite    │ │  3x-ui #1  │ │  3x-ui #N  │
   │  daralla.db│ │  (сервер)  │ │  (сервер)  │
   └────────────┘ └────────────┘ └────────────┘
```

---

## Быстрый старт

### Требования

- Python 3.11+
- Доступ к API панели 3x-ui на VPN-серверах

### Установка

```bash
git clone <repo-url> && cd Daralla
python -m venv venv
venv/Scripts/activate        # Windows
# source venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
```

### Конфигурация

```bash
cp .env.example .env
```

Обязательные переменные:

| Переменная | Описание |
|---|---|
| `TELEGRAM_TOKEN` | Токен бота от [@BotFather](https://t.me/BotFather) |
| `ADMIN_ID` | Telegram ID администратора(ов), через запятую |
| `YOOKASSA_SHOP_ID` | ID магазина YooKassa |
| `YOOKASSA_SECRET_KEY` | Секретный ключ YooKassa |
| `WEBHOOK_URL` | HTTPS-URL для вебхуков (`https://домен/webhook/yookassa`) |
| `WEBAPP_URL` | URL мини-приложения (`https://домен/`) |

<details>
<summary>Все переменные окружения</summary>

| Переменная | По умолчанию | Описание |
|---|---|---|
| `VPN_BRAND_NAME` | `Daralla VPN` | Название бренда |
| `BOT_USERNAME` | — | Username бота для ссылок |
| `WEBHOOK_PORT` | `5000` | Порт веб-сервера |
| `WEBSITE_URL` | — | URL сайта |
| `AUTH_COOKIE_DOMAIN` | — | Домен cookie для SSO (`.daralla.ru`) |
| `PRICE_MONTH` | `150` | Цена 1 месяц (RUB) |
| `PRICE_3MONTH` | `350` | Цена 3 месяца (RUB) |
| `CRYPTOCLOUD_API_TOKEN` | — | API-токен CryptoCloud (опционально) |
| `CRYPTOCLOUD_SHOP_ID` | — | Shop ID CryptoCloud |
| `CRYPTOCLOUD_WEBHOOK_SECRET` | — | JWT-секрет CryptoCloud |
| `EVENTS_MODULE_ENABLED` | `0` | Включить модуль событий (`1`/`true`) |
| `IMAGE_MAIN_MENU` | `images/main_menu.jpg` | Изображение главного меню |
| `IMAGE_PAYMENT_SUCCESS` | `images/payment_success.jpg` | Изображение успешной оплаты |
| `IMAGE_PAYMENT_FAILED` | `images/payment_failed.jpg` | Изображение ошибки оплаты |
| `NGROK_AUTH_TOKEN` | — | Токен Ngrok для локальной разработки |

</details>

### Запуск

```bash
python -m bot
```

Стартуют:
- Telegram-бот (polling)
- Quart/Hypercorn на порту `WEBHOOK_PORT` (вебхуки + веб-приложение)

Служебные endpoints:
- `GET /health` — liveness
- `GET /ready` — readiness (БД и runtime-контекст)
- `GET /metrics` — базовые счетчики API/webhook/background-задач

---

## Docker

```bash
docker build -t daralla .
docker run --env-file .env -p 5000:5000 -v daralla_data:/app/data daralla
```

Или через docker-compose:

```bash
docker-compose up -d
```

> HTTPS-терминацию (nginx, traefik, Caddy) настраивайте отдельно перед контейнером.

---

## Структура проекта

```
Daralla/
├── apps/
│   ├── backend/            # Зона владения backend (переходный слой, runtime без изменений)
│   └── frontend/           # Зона владения frontend (переходный слой, runtime без изменений)
├── bot/
│   ├── bot.py              # Точка входа
│   ├── handlers/           # Команды и callback Telegram
│   ├── services/           # X-UI API, подписки, синхронизация, уведомления
│   ├── db/                 # Модули работы с БД (users, subscriptions, servers, notifications, payments)
│   ├── web/
│   │   └── routes/         # Quart-маршруты: webhook, API, админка
│   ├── events/             # Модуль реферальных событий (опционально)
│   └── utils.py            # Утилиты и хелперы
├── webapp/
│   ├── index.html          # SPA — Mini App и веб-клиент
│   ├── app.js              # Клиентская логика
│   └── style.css           # Стили
├── shared/
│   └── contracts/          # API-контракты и примеры payload для FE/BE
├── images/                 # Изображения для меню бота
├── scripts/                # Вспомогательные скрипты
├── tests/                  # Тесты (pytest)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

> Примечание: проект остается единым runtime-сервисом. Каталоги `apps/*` и `shared/contracts` введены как безопасный этап разделения зон ответственности frontend/backend без поломки текущих путей `bot/` и `webapp/`.

---

## Тесты

```bash
pytest
```

Unit- и integration-тесты для БД, Quart-маршрутов и платежей (`pytest` + `pytest-asyncio`).

Архитектурные проверки:

```bash
python scripts/check_arch_rules.py
python scripts/check_frontend_smoke.py
```

Контракты API между frontend/backend:

```bash
shared/contracts/http_contracts_v1.json
```

---

## Технологии

| Компонент | Технология |
|---|---|
| Бот | python-telegram-bot 20.7 |
| Веб-сервер | Quart + Hypercorn (ASGI) |
| База данных | SQLite через aiosqlite |
| Оплата | YooKassa SDK, CryptoCloud API |
| VPN-панели | py3xui (3x-ui API) |
| HTTP-клиент | httpx, requests |
| Деплой | Docker, docker-compose |

---

## Лицензия

Проприетарный проект. Все права защищены.
