"""Service helpers for user payment routes."""

from __future__ import annotations

import os
import time
import uuid
from urllib.parse import urlencode

import aiosqlite
import httpx

from daralla_backend.db import DB_PATH, add_payment, get_payment_by_id
from daralla_backend.platega_config import (
    PLATEGA_BASE_URL,
    PLATEGA_CREATE_PATH,
    PLATEGA_CURRENCY,
    PLATEGA_FAILED_URL,
    PLATEGA_MERCHANT_ID,
    PLATEGA_PAYMENT_METHOD,
    PLATEGA_RETURN_URL,
    PLATEGA_SECRET,
)
from daralla_backend.db.subscriptions_db import (
    get_subscription_by_id,
    get_subscription_traffic_quota,
    subscription_should_show_user_traffic_quota,
)
from daralla_backend.cryptocloud_config import CRYPTOCLOUD_AVAILABLE_CURRENCIES
from daralla_backend.prices_config import (
    PRICES,
    get_default_device_limit_async,
    get_tariff,
    get_traffic_topup_package,
    refresh_prices_from_db,
)
from daralla_backend.web.routes.api_user_helpers import cryptocloud_extract_address


class UserPaymentServiceError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


async def get_user_subscription_for_extension(subscription_id: int, user_id: str):
    return await get_subscription_by_id(subscription_id, user_id)


async def cancel_pending_user_payments(user_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE payments SET status = ? WHERE user_id = ? AND status = ?",
            ("canceled", user_id, "pending"),
        )
        await db.commit()


async def create_pending_payment(payment_id: str, user_id: str, meta: dict) -> None:
    await add_payment(payment_id=payment_id, user_id=user_id, status="pending", meta=meta)


async def fetch_payment_by_id(payment_id: str):
    return await get_payment_by_id(payment_id)


async def create_user_payment(
    user_id: str,
    period: str,
    subscription_id,
    referrer_code: str,
    gateway: str,
    gateway_method: str,
    logger,
):
    period = str(period or "").strip().lower()
    tariff = get_tariff(period)
    if not period or not tariff:
        raise UserPaymentServiceError("Invalid period", 400)
    if gateway not in ("yookassa", "cryptocloud", "platega"):
        gateway = "yookassa"

    if subscription_id:
        sub = await get_user_subscription_for_extension(int(subscription_id), user_id)
        if not sub:
            raise UserPaymentServiceError("Подписка не найдена или вам недоступна", 404)
        if sub.get("status") == "deleted":
            raise UserPaymentServiceError(
                "Подписка удалена. Продление невозможно. Оформите новую подписку.",
                400,
            )

    referrer_user_id = None
    if referrer_code:
        try:
            from daralla_backend.events.db.queries import get_user_id_by_code

            referrer_user_id = await get_user_id_by_code(referrer_code)
            if referrer_user_id and referrer_user_id == user_id:
                raise UserPaymentServiceError("Нельзя использовать свой код", 400)
        except UserPaymentServiceError:
            raise
        except Exception:
            referrer_user_id = None

    default_dl = await get_default_device_limit_async()
    tariff_price = float(tariff.get("price", PRICES.get(period, 0)) or 0)
    tariff_days = int(tariff.get("days", 30) or 30)
    price = f"{tariff_price:.2f}"
    await cancel_pending_user_payments(user_id)

    subscription_uuid = str(uuid.uuid4())
    unique_email = f"{user_id}_{subscription_uuid}"
    payment_period = f"extend_sub_{period}" if subscription_id else period
    payment_meta_base = {
        "price": price,
        "type": payment_period,
        "unique_email": unique_email,
        "message_id": None,
        "device_limit": default_dl,
        "period_days": tariff_days,
    }
    if subscription_id:
        payment_meta_base["extension_subscription_id"] = int(subscription_id)
    if referrer_user_id:
        payment_meta_base["referrer_user_id"] = referrer_user_id

    if gateway == "cryptocloud":
        api_token = os.getenv("CRYPTOCLOUD_API_TOKEN")
        shop_id = os.getenv("CRYPTOCLOUD_SHOP_ID")
        if not api_token or not shop_id:
            logger.warning("CryptoCloud payment is not configured: missing token or shop_id")
            raise UserPaymentServiceError("CryptoCloud payment is not configured", 503)
        amount_rub = tariff_price
        order_id = f"{user_id}_{int(time.time() * 1000)}"
        payload = {
            "shop_id": shop_id,
            "amount": amount_rub,
            "currency": "RUB",
            "order_id": order_id,
            "add_fields": {
                "time_to_pay": {"hours": 0, "minutes": 15},
                "available_currencies": list(CRYPTOCLOUD_AVAILABLE_CURRENCIES),
            },
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.cryptocloud.plus/v2/invoice/create",
                headers={"Authorization": f"Token {api_token}", "Content-Type": "application/json"},
                json=payload,
            )
            if resp.status_code != 200:
                logger.warning("CryptoCloud invoice create failed: %s %s", resp.status_code, resp.text)
                raise UserPaymentServiceError("Failed to create crypto invoice", 502)
            body = resp.json()
            if body.get("status") != "success" or "result" not in body:
                logger.warning("CryptoCloud invoice create error: %s", body)
                raise UserPaymentServiceError("Failed to create crypto invoice", 502)
            result = body["result"]
            invoice_uuid = result.get("uuid")
            payment_link = result.get("link")
            if not invoice_uuid or not payment_link:
                logger.warning("CryptoCloud missing uuid/link: %s", result)
                raise UserPaymentServiceError("Invalid crypto invoice response", 502)
            payment_meta_base["gateway"] = "cryptocloud"
            addr = cryptocloud_extract_address(result)

        crypto_amt = result.get("amount") if isinstance(result, dict) else None
        if crypto_amt is not None:
            payment_meta_base["crypto_amount"] = str(crypto_amt)
        currency_obj = result.get("currency") if isinstance(result.get("currency"), dict) else {}
        network_obj = currency_obj.get("network") if isinstance(currency_obj.get("network"), dict) else {}
        cc_from_api = (
            result.get("cryptocurrency")
            or result.get("currency_code")
            or currency_obj.get("fullcode")
            or currency_obj.get("code")
        )
        if cc_from_api:
            payment_meta_base["cryptocurrency"] = str(cc_from_api).strip().upper()
        crypto_out = None
        if addr:
            crypto_out = {
                "address": addr,
                "amount": crypto_amt,
                "expiry_date": result.get("expiry_date"),
                "currency_code": currency_obj.get("code") or currency_obj.get("fullcode"),
                "network_name": network_obj.get("fullname") or network_obj.get("code"),
                "network_code": network_obj.get("code"),
            }
        else:
            logger.info(
                "CryptoCloud: пустой address в ответе create для %s — клиент использует payment_url",
                invoice_uuid,
            )

        await create_pending_payment(payment_id=invoice_uuid, user_id=user_id, meta=payment_meta_base)
        return {
            "success": True,
            "payment_id": invoice_uuid,
            "payment_url": payment_link,
            "amount": price,
            "period": period,
            "cryptocurrency": payment_meta_base.get("cryptocurrency"),
            "crypto": crypto_out,
            "h2h_available": bool(crypto_out),
        }

    if gateway == "platega":
        if not PLATEGA_MERCHANT_ID or not PLATEGA_SECRET:
            logger.warning("Platega payment is not configured: missing merchant_id or secret")
            raise UserPaymentServiceError("Platega payment is not configured", 503)

        webapp_base = (os.getenv("WEBAPP_URL") or "").strip().rstrip("/")
        default_return_url = f"{webapp_base}/?{urlencode({'payment_return': '1'})}" if webapp_base else ""
        default_failed_url = f"{webapp_base}/?{urlencode({'payment_return': '0'})}" if webapp_base else ""
        return_url = (PLATEGA_RETURN_URL or default_return_url).strip()
        failed_url = (PLATEGA_FAILED_URL or default_failed_url).strip()
        if not return_url or not failed_url:
            logger.error("PLATEGA return/failed URL is missing")
            raise UserPaymentServiceError("Platega redirect URLs are not configured", 503)

        amount_rub = tariff_price
        normalized_method = (gateway_method or "").strip().lower()
        platega_method = PLATEGA_PAYMENT_METHOD
        platega_method_label = "custom"
        if normalized_method == "sbp":
            platega_method = 2
            platega_method_label = "sbp"
        elif normalized_method == "crypto":
            platega_method = 13
            platega_method_label = "crypto"
        payload = {
            "paymentMethod": platega_method,
            "paymentDetails": {"amount": amount_rub, "currency": PLATEGA_CURRENCY},
            "description": f"VPN {period} для {user_id}",
            "return": return_url,
            "failedUrl": failed_url,
            "payload": f"user_id={user_id};type={payment_period};email={unique_email}",
        }
        target_url = f"{PLATEGA_BASE_URL}{PLATEGA_CREATE_PATH}"
        logger.info(
            "Platega create transaction request: url=%s method=%s method_label=%s currency=%s",
            target_url,
            platega_method,
            platega_method_label,
            PLATEGA_CURRENCY,
        )

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    target_url,
                    headers={
                        "X-MerchantId": PLATEGA_MERCHANT_ID,
                        "X-Secret": PLATEGA_SECRET,
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if resp.status_code >= 400:
                    logger.warning("Platega create transaction failed: %s %s", resp.status_code, resp.text)
                    raise UserPaymentServiceError("Failed to create Platega transaction", 502)
                try:
                    body = resp.json()
                except ValueError:
                    logger.warning("Platega create transaction invalid JSON: %s", resp.text)
                    raise UserPaymentServiceError("Invalid Platega response", 502)
        except httpx.HTTPError as exc:
            logger.warning(
                "Platega create transaction network error: url=%s error=%s",
                target_url,
                exc,
            )
            raise UserPaymentServiceError("Platega temporarily unavailable", 502)

        result = body.get("result") if isinstance(body.get("result"), dict) else body
        transaction_id = (
            result.get("id")
            or result.get("transactionId")
            or result.get("transaction_id")
            or result.get("uuid")
        )
        payment_link = (
            result.get("redirect")
            or result.get("redirectUrl")
            or result.get("redirect_url")
            or result.get("payment_url")
            or result.get("payUrl")
            or result.get("pay_url")
            or result.get("url")
        )
        if not transaction_id or not payment_link:
            logger.warning("Platega create transaction invalid response: %s", body)
            raise UserPaymentServiceError("Invalid Platega response", 502)

        payment_meta_base["gateway"] = "platega"
        payment_meta_base["gateway_method"] = platega_method_label
        await create_pending_payment(
            payment_id=str(transaction_id).strip(),
            user_id=user_id,
            meta=payment_meta_base,
        )
        return {
            "success": True,
            "payment_id": str(transaction_id).strip(),
            "payment_url": str(payment_link).strip(),
            "amount": price,
            "period": period,
            "gateway": "platega",
            "gateway_method": platega_method_label,
        }

    from yookassa import Payment

    webapp_base = (os.getenv("WEBAPP_URL") or "").strip().rstrip("/")
    if not webapp_base:
        logger.error("WEBAPP_URL не задан — для ЮKassa redirect нужен return_url")
        raise UserPaymentServiceError("Платёж временно недоступен", 503)

    yookassa_return_url = f"{webapp_base}/?{urlencode({'payment_return': '1'})}"
    payment = Payment.create(
        {
            "amount": {"value": price, "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": yookassa_return_url},
            "capture": True,
            "description": f"VPN {period} для {user_id}",
            "metadata": {
                "user_id": user_id,
                "type": payment_period,
                "device_limit": default_dl,
                "unique_email": unique_email,
                "price": price,
            },
            "receipt": {
                "customer": {"email": f"{user_id}@vpn-x3.ru"},
                "items": [
                    {
                        "description": f"VPN {period} для {user_id}",
                        "quantity": "1.00",
                        "amount": {"value": price, "currency": "RUB"},
                        "vat_code": 1,
                    }
                ],
            },
        }
    )
    confirmation = getattr(payment, "confirmation", None)
    pay_url = getattr(confirmation, "confirmation_url", None) if confirmation else None
    if not pay_url or not str(pay_url).strip().lower().startswith("http"):
        logger.error(
            "YooKassa redirect: нет confirmation_url в ответе, payment_id=%s, confirmation=%r",
            getattr(payment, "id", None),
            confirmation,
        )
        raise UserPaymentServiceError("Не удалось создать платёж", 502)

    await create_pending_payment(payment_id=payment.id, user_id=user_id, meta=payment_meta_base)
    return {
        "success": True,
        "payment_id": payment.id,
        "payment_url": str(pay_url).strip(),
        "amount": price,
        "period": period,
        "gateway": "yookassa",
    }


async def create_user_traffic_topup_payment(
    user_id: str,
    subscription_id: int,
    traffic_package_id: str,
    referrer_code: str,
    gateway: str,
    gateway_method: str,
    logger,
):
    """Платёж докупки трафика: цена и объём только из конфиг-пакета на сервере."""
    await refresh_prices_from_db()
    pkg_id = str(traffic_package_id or "").strip().lower()
    pkg = get_traffic_topup_package(pkg_id)
    if not pkg:
        raise UserPaymentServiceError("Неизвестный пакет докупки трафика", 400)
    if gateway not in ("yookassa", "cryptocloud", "platega"):
        gateway = "yookassa"

    sub = await get_user_subscription_for_extension(int(subscription_id), user_id)
    if not sub:
        raise UserPaymentServiceError("Подписка не найдена или вам недоступна", 404)
    if sub.get("status") == "deleted":
        raise UserPaymentServiceError(
            "Подписка удалена. Докупка трафика недоступна.",
            400,
        )

    quota = await get_subscription_traffic_quota(int(subscription_id))
    if not quota:
        raise UserPaymentServiceError(
            "Докупка трафика недоступна: подписка без лимитного учёта по группе.",
            400,
        )
    if not await subscription_should_show_user_traffic_quota(int(subscription_id), dict(quota)):
        raise UserPaymentServiceError(
            "Докупка трафика недоступна: ни одна нода не привязана к лимитному пакету трафика.",
            400,
        )

    referrer_user_id = None
    referrer_code = (referrer_code or "").strip()
    if referrer_code:
        try:
            from daralla_backend.events.db.queries import get_user_id_by_code

            referrer_user_id = await get_user_id_by_code(referrer_code)
            if referrer_user_id and referrer_user_id == user_id:
                raise UserPaymentServiceError("Нельзя использовать свой код", 400)
        except UserPaymentServiceError:
            raise
        except Exception:
            referrer_user_id = None

    default_dl = await get_default_device_limit_async()
    tariff_price = float(pkg["price"])
    price = f"{tariff_price:.2f}"
    bytes_total = int(pkg["bytes_total"])
    unique_email = f"{user_id}_{int(subscription_id)}_tu_{uuid.uuid4().hex[:12]}"
    payment_meta_base = {
        "price": price,
        "type": "traffic_topup",
        "purchase_kind": "traffic_topup",
        "traffic_topup_bytes": bytes_total,
        "traffic_topup_package_id": pkg["id"],
        "extension_subscription_id": int(subscription_id),
        "unique_email": unique_email,
        "message_id": None,
        "device_limit": default_dl,
        "period_days": 0,
    }
    if referrer_user_id:
        payment_meta_base["referrer_user_id"] = referrer_user_id

    await cancel_pending_user_payments(user_id)

    desc_short = f"Трафик «{pkg['title']}»"
    desc_user = f"{desc_short}, подписка {subscription_id}"

    if gateway == "cryptocloud":
        api_token = os.getenv("CRYPTOCLOUD_API_TOKEN")
        shop_id = os.getenv("CRYPTOCLOUD_SHOP_ID")
        if not api_token or not shop_id:
            logger.warning("CryptoCloud payment is not configured: missing token or shop_id")
            raise UserPaymentServiceError("CryptoCloud payment is not configured", 503)
        amount_rub = tariff_price
        order_id = f"{user_id}_{int(time.time() * 1000)}"
        payload = {
            "shop_id": shop_id,
            "amount": amount_rub,
            "currency": "RUB",
            "order_id": order_id,
            "add_fields": {
                "time_to_pay": {"hours": 0, "minutes": 15},
                "available_currencies": list(CRYPTOCLOUD_AVAILABLE_CURRENCIES),
            },
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.cryptocloud.plus/v2/invoice/create",
                headers={"Authorization": f"Token {api_token}", "Content-Type": "application/json"},
                json=payload,
            )
            if resp.status_code != 200:
                logger.warning("CryptoCloud invoice create failed: %s %s", resp.status_code, resp.text)
                raise UserPaymentServiceError("Failed to create crypto invoice", 502)
            body = resp.json()
            if body.get("status") != "success" or "result" not in body:
                logger.warning("CryptoCloud invoice create error: %s", body)
                raise UserPaymentServiceError("Failed to create crypto invoice", 502)
            result = body["result"]
            invoice_uuid = result.get("uuid")
            payment_link = result.get("link")
            if not invoice_uuid or not payment_link:
                logger.warning("CryptoCloud missing uuid/link: %s", result)
                raise UserPaymentServiceError("Invalid crypto invoice response", 502)
            payment_meta_base["gateway"] = "cryptocloud"
            addr = cryptocloud_extract_address(result)

        crypto_amt = result.get("amount") if isinstance(result, dict) else None
        if crypto_amt is not None:
            payment_meta_base["crypto_amount"] = str(crypto_amt)
        currency_obj = result.get("currency") if isinstance(result.get("currency"), dict) else {}
        network_obj = currency_obj.get("network") if isinstance(currency_obj.get("network"), dict) else {}
        cc_from_api = (
            result.get("cryptocurrency")
            or result.get("currency_code")
            or currency_obj.get("fullcode")
            or currency_obj.get("code")
        )
        if cc_from_api:
            payment_meta_base["cryptocurrency"] = str(cc_from_api).strip().upper()
        crypto_out = None
        if addr:
            crypto_out = {
                "address": addr,
                "amount": crypto_amt,
                "expiry_date": result.get("expiry_date"),
                "currency_code": currency_obj.get("code") or currency_obj.get("fullcode"),
                "network_name": network_obj.get("fullname") or network_obj.get("code"),
                "network_code": network_obj.get("code"),
            }

        await create_pending_payment(payment_id=invoice_uuid, user_id=user_id, meta=payment_meta_base)
        return {
            "success": True,
            "payment_id": invoice_uuid,
            "payment_url": payment_link,
            "amount": price,
            "period": "traffic_topup",
            "traffic_topup": True,
            "traffic_package_id": pkg["id"],
            "cryptocurrency": payment_meta_base.get("cryptocurrency"),
            "crypto": crypto_out,
            "h2h_available": bool(crypto_out),
        }

    if gateway == "platega":
        if not PLATEGA_MERCHANT_ID or not PLATEGA_SECRET:
            logger.warning("Platega payment is not configured: missing merchant_id or secret")
            raise UserPaymentServiceError("Platega payment is not configured", 503)

        webapp_base = (os.getenv("WEBAPP_URL") or "").strip().rstrip("/")
        default_return_url = f"{webapp_base}/?{urlencode({'payment_return': '1'})}" if webapp_base else ""
        default_failed_url = f"{webapp_base}/?{urlencode({'payment_return': '0'})}" if webapp_base else ""
        return_url = (PLATEGA_RETURN_URL or default_return_url).strip()
        failed_url = (PLATEGA_FAILED_URL or default_failed_url).strip()
        if not return_url or not failed_url:
            logger.error("PLATEGA return/failed URL is missing")
            raise UserPaymentServiceError("Platega redirect URLs are not configured", 503)

        amount_rub = tariff_price
        normalized_method = (gateway_method or "").strip().lower()
        platega_method = PLATEGA_PAYMENT_METHOD
        platega_method_label = "custom"
        if normalized_method == "sbp":
            platega_method = 2
            platega_method_label = "sbp"
        elif normalized_method == "crypto":
            platega_method = 13
            platega_method_label = "crypto"
        payload = {
            "paymentMethod": platega_method,
            "paymentDetails": {"amount": amount_rub, "currency": PLATEGA_CURRENCY},
            "description": f"{desc_user} для {user_id}",
            "return": return_url,
            "failedUrl": failed_url,
            "payload": f"user_id={user_id};type=traffic_topup;email={unique_email}",
        }
        target_url = f"{PLATEGA_BASE_URL}{PLATEGA_CREATE_PATH}"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    target_url,
                    headers={
                        "X-MerchantId": PLATEGA_MERCHANT_ID,
                        "X-Secret": PLATEGA_SECRET,
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if resp.status_code >= 400:
                    logger.warning("Platega create transaction failed: %s %s", resp.status_code, resp.text)
                    raise UserPaymentServiceError("Failed to create Platega transaction", 502)
                try:
                    body = resp.json()
                except ValueError:
                    logger.warning("Platega create transaction invalid JSON: %s", resp.text)
                    raise UserPaymentServiceError("Invalid Platega response", 502)
        except httpx.HTTPError as exc:
            logger.warning("Platega create transaction network error: url=%s error=%s", target_url, exc)
            raise UserPaymentServiceError("Platega temporarily unavailable", 502)

        result = body.get("result") if isinstance(body.get("result"), dict) else body
        transaction_id = (
            result.get("id")
            or result.get("transactionId")
            or result.get("transaction_id")
            or result.get("uuid")
        )
        payment_link = (
            result.get("redirect")
            or result.get("redirectUrl")
            or result.get("redirect_url")
            or result.get("payment_url")
            or result.get("payUrl")
            or result.get("pay_url")
            or result.get("url")
        )
        if not transaction_id or not payment_link:
            logger.warning("Platega create transaction invalid response: %s", body)
            raise UserPaymentServiceError("Invalid Platega response", 502)

        payment_meta_base["gateway"] = "platega"
        payment_meta_base["gateway_method"] = platega_method_label
        await create_pending_payment(
            payment_id=str(transaction_id).strip(),
            user_id=user_id,
            meta=payment_meta_base,
        )
        return {
            "success": True,
            "payment_id": str(transaction_id).strip(),
            "payment_url": str(payment_link).strip(),
            "amount": price,
            "period": "traffic_topup",
            "traffic_topup": True,
            "traffic_package_id": pkg["id"],
            "gateway": "platega",
            "gateway_method": platega_method_label,
        }

    from yookassa import Payment

    webapp_base = (os.getenv("WEBAPP_URL") or "").strip().rstrip("/")
    if not webapp_base:
        logger.error("WEBAPP_URL не задан — для ЮKassa redirect нужен return_url")
        raise UserPaymentServiceError("Платёж временно недоступен", 503)

    yookassa_return_url = f"{webapp_base}/?{urlencode({'payment_return': '1'})}"
    payment = Payment.create(
        {
            "amount": {"value": price, "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": yookassa_return_url},
            "capture": True,
            "description": f"{desc_user} для {user_id}",
            "metadata": {
                "user_id": user_id,
                "type": "traffic_topup",
                "purchase_kind": "traffic_topup",
                "device_limit": default_dl,
                "unique_email": unique_email,
                "price": price,
                "extension_subscription_id": str(int(subscription_id)),
                "traffic_topup_bytes": str(bytes_total),
                "traffic_topup_package_id": pkg["id"],
            },
            "receipt": {
                "customer": {"email": f"{user_id}@vpn-x3.ru"},
                "items": [
                    {
                        "description": desc_user[:128],
                        "quantity": "1.00",
                        "amount": {"value": price, "currency": "RUB"},
                        "vat_code": 1,
                    }
                ],
            },
        }
    )
    confirmation = getattr(payment, "confirmation", None)
    pay_url = getattr(confirmation, "confirmation_url", None) if confirmation else None
    if not pay_url or not str(pay_url).strip().lower().startswith("http"):
        logger.error(
            "YooKassa redirect: нет confirmation_url в ответе, payment_id=%s, confirmation=%r",
            getattr(payment, "id", None),
            confirmation,
        )
        raise UserPaymentServiceError("Не удалось создать платёж", 502)

    await create_pending_payment(payment_id=payment.id, user_id=user_id, meta=payment_meta_base)
    return {
        "success": True,
        "payment_id": payment.id,
        "payment_url": str(pay_url).strip(),
        "amount": price,
        "period": "traffic_topup",
        "traffic_topup": True,
        "traffic_package_id": pkg["id"],
        "gateway": "yookassa",
    }


async def user_payment_status_payload(user_id: str, payment_id: str):
    payment_info = await fetch_payment_by_id(payment_id)
    if not payment_info:
        raise UserPaymentServiceError("Payment not found", 404)
    if payment_info["user_id"] != user_id:
        raise UserPaymentServiceError("Access denied", 403)
    return {
        "success": True,
        "payment_id": payment_id,
        "status": payment_info["status"],
        "activated": bool(payment_info.get("activated", 0)),
    }
