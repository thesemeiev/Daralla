---
name: Интеграция CryptoCloud оплаты
overview: "Добавить приём криптоплатежей через CryptoCloud как второй платёжный канал: создание инвойса по API, webhook (postback) с проверкой JWT, переиспользование существующей логики активации подписки. Без изменения схемы таблицы payments; фронт — выбор «картой» или «криптой» и отображение ссылки на оплату."
todos: []
isProject: false
---

# План: интеграция крипто-оплаты CryptoCloud

## Источники

- [CryptoCloud: создание инвойса](https://docs.cryptocloud.plus/en/api-reference-v2/create-invoice) — `POST https://api.cryptocloud.plus/v2/invoice/create`, тело: `shop_id`, `amount`, `currency` (RUB поддерживается), опционально `order_id`, `add_fields` (например `cryptocurrency: "USDT_TRC20"`). Ответ: `result.uuid` (ID инвойса, префикс INV-), `result.link` (ссылка на оплату), `result.status`.
- [CryptoCloud: Automatic POSTBACK](https://docs.cryptocloud.plus/en/api-reference-v2/postback) — после оплаты на указанный в проекте URL уходит POST с полями `status`, `invoice_id`, `invoice_info.uuid`, `order_id`, `token` (JWT, подпись секретом из настроек проекта, алгоритм HS256). Ответ 200 обязателен; обработку выполнять в фоне.

Текущий поток YooKassa: [api_user.py](webapp/../bot/web/routes/api_user.py) создаёт платёж и пишет в [payments](webapp/../bot/db/payments_db.py) (`payment_id`, `user_id`, `status`, `meta`), возвращает `payment_url`; [payment.py](webapp/../bot/web/routes/payment.py) принимает webhook и вызывает [process_payment_webhook](webapp/../bot/handlers/api_support/payment_processors.py), который по `payment_id` находит платёж и при `status == 'succeeded'` вызывает `process_successful_payment` (создание/продление подписки). Эту же цепочку используем для CryptoCloud.

---

## 1. Конфигурация и окружение

- В [.env.example](.env.example) и в коде добавить переменные:
  - `CRYPTOCLOUD_API_TOKEN` — токен API (Authorization: Token &lt;token&gt;).
  - `CRYPTOCLOUD_SHOP_ID` — идентификатор магазина из личного кабинета CryptoCloud.
  - `CRYPTOCLOUD_WEBHOOK_SECRET` — секрет для проверки JWT в postback (из настроек проекта в CryptoCloud).
- В личном кабинете CryptoCloud: указать URL постбэка (например `https://&lt;ваш-домен&gt;/webhook/cryptocloud`), сохранить секрет для подписи.
- Цены: в [prices_config.py](bot/prices_config.py) сейчас цены в RUB. В API CryptoCloud поле `amount` в документации описано как «в USD», при этом в запросе можно передать `currency: "RUB"`. В плане: при создании инвойса передавать `amount` из `PRICES[period]` и `currency: "RUB"`; если API вернёт ошибку (требует USD), ввести в конфиг курс или отдельные цены в USD для крипты.

---

## 2. Бэкенд: создание инвойса (второй канал)

- В [api_user.py](bot/web/routes/api_user.py) в обработчике `POST /api/user/payment/create`:
  - Принимать в теле опциональный параметр `gateway` со значениями `"yookassa"` (по умолчанию) или `"cryptocloud"`.
  - Ветка для `gateway == "cryptocloud"`:
    - Проверить наличие `CRYPTOCLOUD_API_TOKEN` и `CRYPTOCLOUD_SHOP_ID`; при отсутствии вернуть 503 или 400 с понятным текстом.
    - Сформировать тело запроса к CryptoCloud: `shop_id`, `amount` (из `PRICES[period]`), `currency: "RUB"` (или USD по конфигу при необходимости), `order_id` — уникальный идентификатор заказа (например `user_id + timestamp` или uuid), при желании `add_fields.cryptocurrency` (например `"USDT_TRC20"`).
    - Выполнить `POST https://api.cryptocloud.plus/v2/invoice/create` с заголовками `Authorization: Token &lt;CRYPTOCLOUD_API_TOKEN&gt;`, `Content-Type: application/json`. Использовать `httpx` или `aiohttp` (async), не блокируя event loop.
    - Из ответа взять `result.uuid` (это будет `payment_id` в нашей БД), `result.link` (это будет `payment_url`).
    - В таблицу `payments` записать: `payment_id = result.uuid`, `user_id`, `status = "pending"`, `meta` — те же поля, что и для YooKassa (`type`, `extension_subscription_id`, `referrer_user_id`, `price` и т.д.), плюс в meta можно положить `"gateway": "cryptocloud"` для аналитики.
    - Вернуть клиенту тот же формат, что и для YooKassa: `success`, `payment_id`, `payment_url` (= link), `amount`, `period`.
  - Ветку YooKassa оставить без изменений при `gateway != "cryptocloud"` (или при отсутствии параметра).

Таблицу [payments](bot/db/payments_db.py) не менять: `payment_id` остаётся строкой (для CryptoCloud будет вида `INV-...`).

---

## 3. Бэкенд: webhook CryptoCloud (postback)

- В [payment.py](bot/web/routes/payment.py) (или в отдельном файле blueprint, тогда зарегистрировать в [app_quart.py](bot/web/app_quart.py)) добавить маршрут:
  - `POST /webhook/cryptocloud`
  - Тело запроса: JSON с полями `status`, `invoice_id`, `invoice_info` (внутри `uuid`), `order_id`, `token`.
  - Проверка подписи: извлечь `token` (JWT), проверить подпись с помощью `CRYPTOCLOUD_WEBHOOK_SECRET` (алгоритм HS256). Использовать библиотеку `PyJWT`. При неверной подписи или истёкшем токене вернуть 401 и не обрабатывать.
  - Идентификатор платежа для поиска в БД: использовать `invoice_info.uuid` (или `invoice_id`, если в доке указано, что приходит тот же идентификатор, что и при создании — у нас в БД хранится `result.uuid`). Искать запись в `payments` по `payment_id`.
  - Если запись не найдена — залогировать и вернуть 200 (чтобы CryptoCloud не повторял запрос бесконечно).
  - Если `status == "success"` (успешная оплата в постбэке): в фоне вызвать существующую функцию `process_payment_webhook(bot_app, payment_id, status)` с `payment_id = invoice_info.uuid` и `status = "succeeded"`. Сразу вернуть клиенту 200 и пустое тело или `{"status": "ok"}`.
  - Идемпотентность: как и для YooKassa, внутри `process_payment_webhook` уже есть проверка `is_activated` — повторный постбэк не приведёт к двойной активации.

Логику создания/продления подписки не дублировать: только один вызов `process_payment_webhook`.

---

## 4. Фронтенд: выбор способа оплаты и вызов API

- На страницах покупки/продления подписки (например, [index.html](webapp/index.html) — блоки с кнопками «Купить»/«Продлить» и [app.js](webapp/app.js) — функция `createPayment(period, subscriptionId)`):
  - Добавить выбор способа оплаты: «Картой (YooKassa)» и «Криптой (CryptoCloud)» — радиокнопки или две отдельные кнопки.
  - При вызове `createPayment(period, subscriptionId)` передавать выбранный способ в API: в теле `POST /api/user/payment/create` добавить поле `gateway: "yookassa"` или `gateway: "cryptocloud"`.
  - Ответ API для обоих шлюзов уже единый: `payment_url`, `payment_id`, `amount`, `period`. Текущее отображение страницы оплаты (кнопка «Перейти к оплате», открытие `payment_url`) и опрос статуса через `GET /api/user/payment/status/:id` оставить без изменений; для крипты пользователь перейдёт по ссылке CryptoCloud, оплатит, постбэк обновит статус, фронт при опросе увидит успех.

Итог: минимальные правки — один параметр в запросе создания платежа и UI выбора шлюза.

---

## 5. Зависимости и безопасность

- Установить `PyJWT` (и при необходимости `httpx` или оставить `aiohttp`, если уже есть) в [requirements.txt](requirements.txt).
- Не логировать тело постбэка целиком (в нём может быть токен); логировать только `invoice_info.uuid` и результат проверки подписи.
- В продакшене использовать HTTPS; URL постбэка с HTTPS указать в настройках проекта CryptoCloud.

---

## 6. Порядок внедрения

1. Добавить переменные окружения и конфиг (в т.ч. чтение `CRYPTOCLOUD_*` в коде).
2. Реализовать создание инвойса в `POST /api/user/payment/create` при `gateway=cryptocloud`.
3. Реализовать `POST /webhook/cryptocloud` с проверкой JWT и вызовом `process_payment_webhook`.
4. Добавить на фронт выбор «Картой» / «Криптой» и передачу `gateway` в запрос создания платежа.
5. В личном кабинете CryptoCloud задать URL постбэка и секрет, протестировать создание инвойса и постбэк (при необходимости — тестовый режим CryptoCloud).

После этого крипто-оплата будет вторым каналом рядом с YooKassa с единой логикой активации подписок и без изменения схемы БД.