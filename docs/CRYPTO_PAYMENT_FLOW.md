# Платёж криптой (CryptoCloud) — сводка

## 1. Создание инвойса (API)

**Файл:** `bot/web/routes/api_user.py`

- **Сумма:** в рублях (при `currency: "RUB"` API принимает amount в рублях — 150 или 350).
- **Тело запроса:** `amount` (рубли), `currency: "RUB"`, `shop_id`, `order_id` (внутренний ID платежа), `add_fields`:
  - `available_currencies` — список криптовалют;
  - `time_to_pay: { "hours": 0, "minutes": 15 }` — ссылка действительна 15 минут (как в UI).
- **Ответ:** сохраняем `payment_id = result["uuid"]` (формат `INV-XXXXXXXX`), отдаём фронту `payment_id` и `payment_url` (link).

**Переменные окружения:** `CRYPTOCLOUD_API_TOKEN`, `CRYPTOCLOUD_SHOP_ID`.

---

## 2. Postback (webhook)

**Файл:** `bot/web/routes/payment.py`

- **Маршруты:** `POST /webhook/cryptocloud` и `POST /callback` (оба обрабатывают postback).
- **Верификация:** если задан `CRYPTOCLOUD_WEBHOOK_SECRET`, проверяется JWT из заголовка; при неверной подписи — 401.
- **Поиск платежа:** `uuid` из тела (или `invoice_id`). Поиск по `payment_id` в БД; если не найден и id без префикса `INV-`, пробуем `"INV-" + raw_id`.
- **Обработка:** только если платёж найден в БД — вызывается `_process_webhook(bot_app, payment_id, status)`. Статусы: `paid` → success, `canceled` / истечение срока → canceled, и т.д.
- **Ответ:** всегда 200 (кроме 400/401/500), чтобы CryptoCloud не слал повторные запросы.

Postback приходит после подтверждения в блокчейне (задержка от ~30 сек до нескольких минут, для BTC до ~1 ч). До этого статус «частично оплачен» — норма.

---

## 3. Обработка в бэкенде (payment_processors)

**Файл:** `bot/handlers/api_support/payment_processors.py`

- В начале `process_payment_webhook`: `"cancelled"` приводится к `"canceled"`.
- Платёж берётся из БД по `payment_id`.
- **Успех (`succeeded`):** продление или новая покупка → `update_payment_status('succeeded')`, `update_payment_activation(1)`.
- **Отмена/возврат:** `update_payment_status(status)`, `update_payment_activation(0)`.
- **Ошибка:** `update_payment_status('failed')`, сброс активации.

---

## 4. Фронт и статус

**Файл:** `webapp/app.js`

- Создание: `createPayment` с `gateway: 'cryptocloud'` → получает `payment_id`, `payment_url`.
- После перехода по ссылке запускается опрос: `GET /api/user/payment/status/<payment_id>` каждые 5 сек (макс. 180 проверок).
- Ответ API: `success`, `payment_id`, `status`, `activated`. По `status === 'succeeded'` и `activated === true` показывается успех; по отмене/ошибке — `showPaymentErrorState(message)`.

---

## 5. Что проверить вручную

1. **Env:** `CRYPTOCLOUD_API_TOKEN`, `CRYPTOCLOUD_SHOP_ID`, в проде — `CRYPTOCLOUD_WEBHOOK_SECRET`.
2. **Создание:** выбор крипты → создание платежа → в БД запись с `payment_id = INV-...`, `gateway = cryptocloud`.
3. **Оплата:** переход по ссылке, оплата на стороне CryptoCloud.
4. **Webhook:** postback приходит на `/webhook/cryptocloud` (или `/callback`), JWT проверяется, платёж находится по `INV-...`, статус обновляется.
5. **Опрос:** фронт получает `status: 'succeeded'`, `activated: true` и показывает «Оплата прошла», редирект в подписки.
6. **Отмена/истечение:** отмена или истечение 15 мин → postback с canceled → на фронте сообщение об отмене/истечении и кнопка «Попробовать снова».

---

## 6. Опционально (уже не обязательно)

- Вызов CryptoCloud `POST /v2/invoice/merchant/info` по `uuid` перед активацией подписки — дополнительная проверка на стороне сервера.
- Расширить автотесты/ручные сценарии на полный цикл: создание → оплата → postback → опрос → успех/ошибка в UI.
