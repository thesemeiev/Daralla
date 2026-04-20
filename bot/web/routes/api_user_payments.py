"""Payment handlers extracted from api_user routes."""

import os
import time
import uuid
from urllib.parse import urlencode

from quart import jsonify, request

from bot.cryptocloud_config import CRYPTOCLOUD_AVAILABLE_CURRENCIES
from bot.prices_config import PRICES, get_default_device_limit_async
from bot.services.user_payments_service import (
    cancel_pending_user_payments,
    create_pending_payment,
    fetch_payment_by_id,
    get_user_subscription_for_extension,
)
from bot.web.routes.admin_common import CORS_HEADERS, _cors_headers
from bot.web.routes.api_user_common import options_response_or_none, require_user_id
from bot.web.routes.api_user_helpers import cryptocloud_extract_address


async def handle_api_user_payment_create(_auth, logger):
    opt = options_response_or_none()
    if opt:
        return opt
    try:
        user_id, err = await require_user_id(_auth)
        if err:
            return jsonify(err[0]), err[1]
        data = await request.get_json(silent=True) or {}
        period = data.get("period")
        subscription_id = data.get("subscription_id")
        referrer_code = (data.get("referrer_code") or "").strip()
        gateway = (data.get("gateway") or "yookassa").strip().lower()
        if not period or period not in ("month", "3month"):
            return jsonify({"error": 'Invalid period. Use "month" or "3month"'}), 400
        if subscription_id:
            sub = await get_user_subscription_for_extension(int(subscription_id), user_id)
            if not sub:
                return jsonify({"error": "Подписка не найдена или вам недоступна"}), 404, _cors_headers()
            if sub.get("status") == "deleted":
                return jsonify({"error": "Подписка удалена. Продление невозможно. Оформите новую подписку."}), 400, _cors_headers()
        referrer_user_id = None
        if referrer_code:
            try:
                from bot.events.db.queries import get_user_id_by_code

                referrer_user_id = await get_user_id_by_code(referrer_code)
                if referrer_user_id and referrer_user_id == user_id:
                    return jsonify({"error": "Нельзя использовать свой код"}), 400
            except Exception:
                referrer_user_id = None
        default_dl = await get_default_device_limit_async()
        price = f"{PRICES[period]:.2f}"
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
        }
        if subscription_id:
            payment_meta_base["extension_subscription_id"] = int(subscription_id)
        if referrer_user_id:
            payment_meta_base["referrer_user_id"] = referrer_user_id

        if gateway == "cryptocloud":
            api_token = os.getenv("CRYPTOCLOUD_API_TOKEN")
            shop_id = os.getenv("CRYPTOCLOUD_SHOP_ID")
            if not api_token or not shop_id:
                return jsonify({"error": "CryptoCloud payment is not configured"}), 503
            amount_rub = float(PRICES[period])
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
            import httpx

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.cryptocloud.plus/v2/invoice/create",
                    headers={"Authorization": f"Token {api_token}", "Content-Type": "application/json"},
                    json=payload,
                )
                if resp.status_code != 200:
                    logger.warning("CryptoCloud invoice create failed: %s %s", resp.status_code, resp.text)
                    return jsonify({"error": "Failed to create crypto invoice"}), 502
                body = resp.json()
                if body.get("status") != "success" or "result" not in body:
                    logger.warning("CryptoCloud invoice create error: %s", body)
                    return jsonify({"error": "Failed to create crypto invoice"}), 502
                result = body["result"]
                invoice_uuid = result.get("uuid")
                payment_link = result.get("link")
                if not invoice_uuid or not payment_link:
                    logger.warning("CryptoCloud missing uuid/link: %s", result)
                    return jsonify({"error": "Invalid crypto invoice response"}), 502
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
            resp_body = {
                "success": True,
                "payment_id": invoice_uuid,
                "payment_url": payment_link,
                "amount": price,
                "period": period,
                "cryptocurrency": payment_meta_base.get("cryptocurrency"),
                "crypto": crypto_out,
                "h2h_available": bool(crypto_out),
            }
            return jsonify(resp_body), 200, _cors_headers()

        from yookassa import Payment

        webapp_base = (os.getenv("WEBAPP_URL") or "").strip().rstrip("/")
        if not webapp_base:
            logger.error("WEBAPP_URL не задан — для ЮKassa redirect нужен return_url")
            return jsonify({"error": "Платёж временно недоступен"}), 503, _cors_headers()

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
            return jsonify({"error": "Не удалось создать платёж"}), 502, _cors_headers()

        await create_pending_payment(payment_id=payment.id, user_id=user_id, meta=payment_meta_base)
        return (
            jsonify(
                {
                    "success": True,
                    "payment_id": payment.id,
                    "payment_url": str(pay_url).strip(),
                    "amount": price,
                    "period": period,
                    "gateway": "yookassa",
                }
            ),
            200,
            _cors_headers(),
        )
    except Exception as e:
        logger.error("Ошибка в API /api/user/payment/create: %s", e, exc_info=True)
        return jsonify({"error": "Internal server error"}), 500, _cors_headers()


async def handle_api_user_payment_status(_auth, payment_id, logger):
    opt = options_response_or_none()
    if opt:
        return opt
    try:
        user_id, err = await require_user_id(_auth)
        if err:
            return jsonify(err[0]), err[1]
        payment_info = await fetch_payment_by_id(payment_id)
        if not payment_info:
            return jsonify({"error": "Payment not found"}), 404
        if payment_info["user_id"] != user_id:
            return jsonify({"error": "Access denied"}), 403
        return (
            jsonify(
                {
                    "success": True,
                    "payment_id": payment_id,
                    "status": payment_info["status"],
                    "activated": bool(payment_info.get("activated", 0)),
                }
            ),
            200,
            _cors_headers(),
        )
    except Exception as e:
        logger.error("Ошибка в API /api/user/payment/status/%s: %s", payment_id, e, exc_info=True)
        return jsonify({"error": "Internal server error"}), 500, _cors_headers()
