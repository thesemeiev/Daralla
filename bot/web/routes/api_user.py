"""
Quart Blueprint: /api/user/* and /api/subscriptions.
Async implementation — no asyncio.new_event_loop / run_until_complete.
"""
import datetime
import logging
import os
import time
import uuid
from urllib.parse import urlencode

import aiosqlite
import requests as requests_lib
from quart import Blueprint, request, jsonify, Response
from werkzeug.security import generate_password_hash, check_password_hash

from bot.handlers.api_support.webhook_auth import authenticate_request_async, verify_telegram_init_data
from bot.web.auth_validation import validate_username_format, validate_password_format
from bot.web.routes.admin_common import CORS_HEADERS, _cors_headers
from bot.cryptocloud_config import (
    CRYPTOCLOUD_AVAILABLE_CURRENCIES,
    CRYPTOCLOUD_CURRENCIES_METADATA,
    CRYPTOCLOUD_DEFAULT_CURRENCY,
)
from bot.prices_config import PRICES, get_default_device_limit_async

logger = logging.getLogger(__name__)


def _cryptocloud_extract_address(result):
    """Адрес из result ответа POST /v2/invoice/create (ключ address может быть null или '')."""
    if not isinstance(result, dict):
        return ""
    for key in ("address", "payment_address", "wallet_address", "crypto_address"):
        raw = result.get(key)
        if raw is not None and raw != "":
            if isinstance(raw, str):
                s = raw.strip()
                if s and s.lower() not in ("none", "null"):
                    return s
            else:
                return str(raw).strip()
    for nested_key in ("wallet", "payment", "deposit"):
        block = result.get(nested_key)
        if isinstance(block, dict):
            for key in ("address", "payment_address"):
                x = block.get(key)
                if x is not None and x != "":
                    if isinstance(x, str):
                        s = x.strip()
                        if s:
                            return s
                    else:
                        return str(x).strip()
    return ""


def create_blueprint(bot_app):
    bp = Blueprint("api_user", __name__)

    async def _auth():
        body = await request.get_json(silent=True) or {}
        return await authenticate_request_async(request.headers, request.args, body, request.cookies)

    @bp.route("/api/user/register", methods=["POST", "OPTIONS"])
    async def api_user_register():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            data = await request.get_json(silent=True) or {}
            user_id = await _auth()
            init_data = request.args.get("initData") or data.get("initData")
            tg_user_id = verify_telegram_init_data(init_data) if init_data else None
            if not user_id and tg_user_id:
                user_id = None
            if not user_id and not tg_user_id:
                return jsonify({"error": "Invalid authentication"}), 401

            from bot.db import is_known_user, register_simple_user
            from bot.db.users_db import (
                get_or_create_subscriber,
                get_user_by_id,
                is_known_telegram_id,
                mark_telegram_id_known,
                get_user_by_telegram_id_v2,
                create_telegram_link,
                update_user_telegram_id,
                generate_user_id,
                reconcile_users_telegram_id_with_link,
            )
            from bot.db.subscriptions_db import (
                get_all_active_subscriptions_by_user,
                create_subscription,
                get_subscription_by_id_only,
                is_subscription_active,
            )

            just_created_tg_user = False
            if not user_id and tg_user_id:
                _tg_str = str(tg_user_id)
                _existing = await get_user_by_telegram_id_v2(_tg_str, use_fallback=True)
                if _existing:
                    user_id = _existing["user_id"]
                else:
                    user_id = generate_user_id()
                    just_created_tg_user = True
                    try:
                        await register_simple_user(user_id)
                        await create_telegram_link(_tg_str, user_id)
                        await update_user_telegram_id(user_id, _tg_str)
                        logger.info(
                            "Регистрация нового TG-first пользователя: user_id=%s, telegram_id=%s",
                            user_id,
                            _tg_str,
                        )
                    except aiosqlite.IntegrityError:
                        logger.warning(
                            "Гонка TG-first регистрации (IntegrityError), telegram_id=%s — сверка с telegram_links",
                            _tg_str,
                        )
                        await reconcile_users_telegram_id_with_link(_tg_str)
                        _existing = await get_user_by_telegram_id_v2(_tg_str, use_fallback=True)
                        if not _existing:
                            raise
                        user_id = _existing["user_id"]
                        just_created_tg_user = False
            if not user_id:
                return jsonify({"error": "Invalid authentication"}), 401
            _user = await get_user_by_id(user_id)
            is_web = bool(_user.get("is_web", 0)) if _user else False
            was_known_user = await is_known_user(user_id)
            if tg_user_id:
                was_known_user = was_known_user or await is_known_telegram_id(str(tg_user_id))
            if just_created_tg_user:
                was_known_user = False
            if not just_created_tg_user:
                await register_simple_user(user_id)
            if tg_user_id:
                await mark_telegram_id_known(str(tg_user_id))

            trial_created = False
            subscription_id = None
            if not was_known_user and not is_web:
                try:
                    existing_subs = await get_all_active_subscriptions_by_user(user_id)
                    now = int(time.time())
                    active_subs = [s for s in existing_subs if is_subscription_active(s)]
                    if len(active_subs) == 0:
                        trial_dl = await get_default_device_limit_async()
                        logger.info("Создание пробной подписки для нового пользователя: %s", user_id)
                        subscriber_id = await get_or_create_subscriber(user_id)
                        expires_at = now + (5 * 24 * 60 * 60)
                        subscription_id, token = await create_subscription(
                            subscriber_id=subscriber_id,
                            period="month",
                            device_limit=trial_dl,
                            price=0.0,
                            expires_at=expires_at,
                            name="Пробная подписка",
                        )
                        trial_created = True
                        logger.info("Пробная подписка создана: subscription_id=%s", subscription_id)
                        from bot.app_context import get_ctx
                        _ctx = get_ctx()
                        subscription_manager = _ctx.subscription_manager
                        server_manager = _ctx.server_manager
                        if subscription_manager and server_manager:
                            sub_dict = await get_subscription_by_id_only(subscription_id)
                            group_id = sub_dict.get("group_id") if sub_dict else None
                            servers_for_group = server_manager.get_servers_by_group(group_id)
                            unique_email = f"{user_id}_{subscription_id}"
                            all_configured_servers = [
                                s["name"]
                                for s in servers_for_group
                                if s.get("x3") is not None
                            ]
                            if all_configured_servers:
                                for server_name in all_configured_servers:
                                    try:
                                        await subscription_manager.attach_server_to_subscription(
                                            subscription_id=subscription_id,
                                            server_name=server_name,
                                            client_email=unique_email,
                                            client_id=None,
                                        )
                                    except Exception as attach_e:
                                        if "UNIQUE constraint" not in str(attach_e) and "already exists" not in str(attach_e).lower():
                                            logger.error(
                                                "Ошибка привязки сервера %s: %s",
                                                server_name,
                                                attach_e,
                                            )
                                successful_servers = []
                                for server_name in all_configured_servers:
                                    try:
                                        client_exists, _ =                                         await subscription_manager.ensure_client_on_server(
                                            subscription_id=subscription_id,
                                            server_name=server_name,
                                            client_email=unique_email,
                                            user_id=user_id,
                                            expires_at=expires_at,
                                            token=token,
                                            device_limit=trial_dl,
                                        )
                                        if client_exists:
                                            successful_servers.append(server_name)
                                    except Exception as e:
                                        logger.error(
                                            "Ошибка создания клиента на %s: %s",
                                            server_name,
                                            e,
                                        )
                                logger.info(
                                    "Пробная подписка: создано на %s/%s серверах",
                                    len(successful_servers),
                                    len(all_configured_servers),
                                )
                except Exception as e:
                    logger.error("Ошибка создания пробной подписки: %s", e, exc_info=True)

            return jsonify({
                "success": True,
                "was_new_user": not was_known_user,
                "trial_created": trial_created,
                "subscription_id": subscription_id,
            }), 200, _cors_headers()
        except Exception as e:
            logger.error("Ошибка регистрации пользователя: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500, _cors_headers()

    @bp.route("/api/subscriptions", methods=["GET", "OPTIONS"])
    async def api_subscriptions():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            user_id = await _auth()
            if not user_id:
                return jsonify({"error": "Invalid authentication"}), 401
            from bot.db.subscriptions_db import get_all_subscriptions_by_user, is_subscription_active

            subscriptions = await get_all_subscriptions_by_user(user_id)
            current_time = int(time.time())
            formatted_subs = []
            for sub in subscriptions:
                expires_at = sub["expires_at"]
                is_active = is_subscription_active(sub)
                is_expired = expires_at < current_time
                expiry_datetime = datetime.datetime.fromtimestamp(expires_at)
                created_datetime = datetime.datetime.fromtimestamp(sub["created_at"])
                formatted_subs.append({
                    "id": sub["id"],
                    "name": (sub.get("name") or "").strip() or f"Подписка {sub['id']}",
                    "status": "active" if is_active else ("expired" if is_expired else sub["status"]),
                    "period": sub["period"],
                    "device_limit": sub["device_limit"],
                    "created_at": sub["created_at"],
                    "created_at_formatted": created_datetime.strftime("%d.%m.%Y %H:%M"),
                    "expires_at": expires_at,
                    "expires_at_formatted": expiry_datetime.strftime("%d.%m.%Y %H:%M"),
                    "price": sub["price"],
                    "token": sub["subscription_token"],
                    "days_remaining": max(0, (expires_at - current_time) // (24 * 60 * 60))
                    if is_active
                    else 0,
                })
            formatted_subs.sort(key=lambda x: (x["status"] != "active", -x["created_at"]))
            resp = jsonify({
                "success": True,
                "subscriptions": formatted_subs,
                "total": len(formatted_subs),
                "active": len([s for s in formatted_subs if s["status"] == "active"]),
            })
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            resp.headers["Pragma"] = "no-cache"
            return resp, 200, _cors_headers()
        except Exception as e:
            logger.error("Ошибка в API /api/subscriptions: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500, _cors_headers()

    @bp.route("/api/user/payment/crypto-currencies", methods=["GET", "OPTIONS"])
    async def api_user_payment_crypto_currencies():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            user_id = await _auth()
            if not user_id:
                return jsonify({"error": "Invalid authentication"}), 401
            items = [{"code": c, "label": lbl} for c, lbl in CRYPTOCLOUD_CURRENCIES_METADATA]
            return jsonify({
                "success": True,
                "default_code": CRYPTOCLOUD_DEFAULT_CURRENCY,
                "currencies": items,
            }), 200, _cors_headers()
        except Exception as e:
            logger.error("Ошибка в API /api/user/payment/crypto-currencies: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500, _cors_headers()

    @bp.route("/api/user/payment/create", methods=["POST", "OPTIONS"])
    async def api_user_payment_create():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            user_id = await _auth()
            if not user_id:
                return jsonify({"error": "Invalid authentication"}), 401
            data = await request.get_json(silent=True) or {}
            period = data.get("period")
            subscription_id = data.get("subscription_id")
            referrer_code = (data.get("referrer_code") or "").strip()
            gateway = (data.get("gateway") or "yookassa").strip().lower()
            if not period or period not in ("month", "3month"):
                return jsonify({"error": 'Invalid period. Use "month" or "3month"'}), 400
            # Запрет продления удалённой подписки (защита от устаревшего списка на клиенте)
            if subscription_id:
                from bot.db.subscriptions_db import get_subscription_by_id
                sub = await get_subscription_by_id(int(subscription_id), user_id)
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
            from bot.db import add_payment, DB_PATH
            import aiosqlite

            default_dl = await get_default_device_limit_async()
            price = f"{PRICES[period]:.2f}"
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE payments SET status = ? WHERE user_id = ? AND status = ?",
                    ("canceled", user_id, "pending"),
                )
                await db.commit()

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
                # API Reference: amount + currency (RUB), add_fields.cryptocurrency и available_currencies;
                # при успехе в result — address, amount в крипте, link.
                api_token = os.getenv("CRYPTOCLOUD_API_TOKEN")
                shop_id = os.getenv("CRYPTOCLOUD_SHOP_ID")
                if not api_token or not shop_id:
                    return jsonify({"error": "CryptoCloud payment is not configured"}), 503
                raw_cc = (data.get("cryptocurrency") or "").strip().upper()
                if raw_cc and raw_cc not in CRYPTOCLOUD_AVAILABLE_CURRENCIES:
                    return jsonify({"error": "Неизвестная криптовалюта"}), 400, _cors_headers()
                cc_code = raw_cc if raw_cc in CRYPTOCLOUD_AVAILABLE_CURRENCIES else CRYPTOCLOUD_DEFAULT_CURRENCY
                amount_rub = float(PRICES[period])
                order_id = f"{user_id}_{int(time.time() * 1000)}"
                payload = {
                    "shop_id": shop_id,
                    "amount": amount_rub,
                    "currency": "RUB",
                    "order_id": order_id,
                    "add_fields": {
                        "time_to_pay": {"hours": 0, "minutes": 15},
                        "cryptocurrency": cc_code,
                        "available_currencies": list(CRYPTOCLOUD_AVAILABLE_CURRENCIES),
                    },
                }
                import httpx
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        "https://api.cryptocloud.plus/v2/invoice/create",
                        headers={
                            "Authorization": f"Token {api_token}",
                            "Content-Type": "application/json",
                        },
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
                    payment_meta_base["cryptocurrency"] = cc_code
                    addr = _cryptocloud_extract_address(result)
                crypto_amt = result.get("amount") if isinstance(result, dict) else None
                if crypto_amt is not None:
                    payment_meta_base["crypto_amount"] = str(crypto_amt)
                currency_obj = result.get("currency") if isinstance(result.get("currency"), dict) else {}
                network_obj = currency_obj.get("network") if isinstance(currency_obj.get("network"), dict) else {}
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
                await add_payment(
                    payment_id=invoice_uuid,
                    user_id=user_id,
                    status="pending",
                    meta=payment_meta_base,
                )
                resp_body = {
                    "success": True,
                    "payment_id": invoice_uuid,
                    "payment_url": payment_link,
                    "amount": price,
                    "period": period,
                    "cryptocurrency": cc_code,
                    "crypto": crypto_out,
                    "h2h_available": bool(crypto_out),
                }
                return jsonify(resp_body), 200, _cors_headers()

            from yookassa import Payment

            payment = Payment.create({
                "amount": {"value": price, "currency": "RUB"},
                "confirmation": {"type": "embedded"},
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
                    "items": [{
                        "description": f"VPN {period} для {user_id}",
                        "quantity": "1.00",
                        "amount": {"value": price, "currency": "RUB"},
                        "vat_code": 1,
                    }],
                },
            })
            confirmation = getattr(payment, "confirmation", None)
            conf_token = getattr(confirmation, "confirmation_token", None) if confirmation else None
            if not conf_token:
                logger.error(
                    "YooKassa embedded: нет confirmation_token в ответе, payment_id=%s",
                    getattr(payment, "id", None),
                )
                return jsonify({"error": "Не удалось создать платёж (виджет)"}), 502, _cors_headers()

            webapp_base = (os.getenv("WEBAPP_URL") or "").strip().rstrip("/")
            widget_return_url = None
            if webapp_base:
                widget_return_url = (
                    f"{webapp_base}/?{urlencode({'payment_return': '1', 'payment_id': payment.id})}"
                )

            await add_payment(
                payment_id=payment.id,
                user_id=user_id,
                status="pending",
                meta=payment_meta_base,
            )
            return jsonify({
                "success": True,
                "payment_id": payment.id,
                "confirmation_token": conf_token,
                "widget_return_url": widget_return_url,
                "amount": price,
                "period": period,
                "gateway": "yookassa",
            }), 200, _cors_headers()
        except Exception as e:
            logger.error("Ошибка в API /api/user/payment/create: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500, _cors_headers()

    @bp.route("/api/user/payment/status/<payment_id>", methods=["GET", "OPTIONS"])
    async def api_user_payment_status(payment_id):
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            user_id = await _auth()
            if not user_id:
                return jsonify({"error": "Invalid authentication"}), 401
            from bot.db import get_payment_by_id

            payment_info = await get_payment_by_id(payment_id)
            if not payment_info:
                return jsonify({"error": "Payment not found"}), 404
            if payment_info["user_id"] != user_id:
                return jsonify({"error": "Access denied"}), 403
            return jsonify({
                "success": True,
                "payment_id": payment_id,
                "status": payment_info["status"],
                "activated": bool(payment_info.get("activated", 0)),
            }), 200, _cors_headers()
        except Exception as e:
            logger.error(
                "Ошибка в API /api/user/payment/status/%s: %s",
                payment_id,
                e,
                exc_info=True,
            )
            return jsonify({"error": "Internal server error"}), 500, _cors_headers()

    @bp.route("/api/user/subscription/<int:sub_id>/rename", methods=["POST", "OPTIONS"])
    async def api_user_subscription_rename(sub_id):
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            user_id = await _auth()
            if not user_id:
                return jsonify({"error": "Invalid authentication"}), 401
            data = await request.get_json(silent=True) or {}
            new_name = (data.get("name") or "").strip()
            if not new_name:
                return jsonify({"error": "Name is required"}), 400
            from bot.db.subscriptions_db import get_subscription_by_id, update_subscription_name

            sub = await get_subscription_by_id(sub_id, user_id)
            if not sub:
                return jsonify({"error": "Subscription not found or access denied"}), 404
            await update_subscription_name(sub_id, new_name)
            return jsonify({
                "success": True,
                "message": "Subscription renamed successfully",
                "name": new_name,
            }), 200, _cors_headers()
        except Exception as e:
            logger.error(
                "Ошибка в API /api/user/subscription/%s/rename: %s",
                sub_id,
                e,
                exc_info=True,
            )
            return jsonify({"error": "Internal server error"}), 500, _cors_headers()

    @bp.route("/api/user/server-usage", methods=["GET", "OPTIONS"])
    async def api_user_server_usage():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            user_id = await _auth()
            if not user_id:
                return jsonify({"error": "Invalid authentication"}), 401
            from bot.db.users_db import get_user_server_usage
            from bot.app_context import get_ctx

            server_usage = await get_user_server_usage(user_id)
            server_manager = get_ctx().server_manager
            servers_info = []
            if server_manager:
                health_status = server_manager.get_server_health_status()
                for server in server_manager.servers:
                    server_name = server["name"]
                    display_name = server["config"].get("display_name", server_name)
                    map_label = server["config"].get("map_label")
                    location = server["config"].get("location") or "Other"
                    lat = server["config"].get("lat")
                    lng = server["config"].get("lng")
                    if lat is not None and lng is not None:
                        usage_data = server_usage.get(server_name, {"count": 0, "percentage": 0})
                        status_info = health_status.get(server_name, {})
                        status = status_info.get("status", "unknown")
                        servers_info.append({
                            "name": server_name,
                            "display_name": display_name,
                            "map_label": map_label,
                            "location": location,
                            "lat": lat,
                            "lng": lng,
                            "usage_count": usage_data["count"],
                            "usage_percentage": usage_data["percentage"],
                            "status": status,
                        })
            return jsonify({"success": True, "servers": servers_info}), 200, _cors_headers()
        except Exception as e:
            logger.error("Ошибка в API /api/user/server-usage: %s", e, exc_info=True)
            return jsonify({"error": "Internal server error"}), 500, _cors_headers()

    @bp.route("/api/user/web-access/setup", methods=["POST", "OPTIONS"])
    async def api_user_web_access_setup():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            data = await request.get_json(silent=True) or {}
            init_data = data.get("initData")
            if not init_data:
                return jsonify({"error": "Telegram data required"}), 400
            telegram_id = verify_telegram_init_data(init_data)
            if not telegram_id:
                return jsonify({"error": "Invalid authentication"}), 401
            username = (data.get("username") or "").strip().lower()
            password = (data.get("password") or "").strip()
            ok, err = validate_username_format(username)
            if not ok:
                return jsonify({"error": err}), 400
            ok, err = validate_password_format(password)
            if not ok:
                return jsonify({"error": err}), 400
            from bot.db.users_db import (
                get_user_by_telegram_id_v2,
                username_available,
                update_user_username,
                update_user_password,
            )

            user = await get_user_by_telegram_id_v2(str(telegram_id), use_fallback=True)
            if not user:
                return jsonify({"error": "Пользователь не найден"}), 404
            user_id = user["user_id"]
            ok = await username_available(username, user_id)
            if not ok:
                return jsonify({"error": "Этот логин уже занят"}), 409
            password_hash = generate_password_hash(password)
            await update_user_username(user_id, username)
            await update_user_password(user_id, password_hash)
            return jsonify({
                "success": True,
                "message": f"Web-доступ настроен. Теперь вы можете войти на сайт с логином {username}.",
                "username": username,
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @bp.route("/api/user/link-telegram/start", methods=["POST", "OPTIONS"])
    async def api_user_link_telegram_start():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            user_id = await _auth()
            if not user_id:
                return jsonify({"error": "Требуется авторизация"}), 401
            from bot.db.users_db import get_user_by_id, link_telegram_create_state

            user = await get_user_by_id(user_id)
            if not user:
                return jsonify({"error": "Пользователь не найден"}), 404
            if user.get("telegram_id"):
                return jsonify({"error": "Telegram уже привязан"}), 400
            state = await link_telegram_create_state(user_id)
            bot_username = os.getenv("BOT_USERNAME", "Daralla_bot").strip()
            link = f"https://t.me/{bot_username}?start=link_{state}"
            return jsonify({"success": True, "link": link, "state": state})
        except Exception as e:
            logger.error("Ошибка link-telegram/start: %s", e, exc_info=True)
            return jsonify({"error": str(e)}), 500

    @bp.route("/api/user/link-status", methods=["GET", "OPTIONS"])
    async def api_user_link_status():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            user_id = await _auth()
            if not user_id:
                return jsonify({"error": "Требуется авторизация"}), 401
            from bot.db.users_db import get_user_by_id

            user = await get_user_by_id(user_id)
            if not user:
                return jsonify({"error": "Пользователь не найден"}), 404
            uid = user.get("user_id")
            tid = user.get("telegram_id")
            is_web = bool(user.get("is_web", 0))
            is_tg_first = not is_web
            telegram_linked = is_tg_first or (is_web and bool(tid))
            display_tid = tid or (uid if (uid and uid.isdigit()) else None)
            # Логин показываем только если пользователь настроил веб-доступ (указал логин)
            username = (user.get("username") or "").strip() or None
            web_access_enabled = bool(user.get("password_hash"))
            return jsonify({
                "success": True,
                "telegram_linked": telegram_linked,
                "is_web": is_web,
                "username": username,
                "user_id": uid,
                "telegram_id": display_tid,
                "web_access_enabled": web_access_enabled,
            })
        except Exception as e:
            logger.error("Ошибка link-status: %s", e, exc_info=True)
            return jsonify({"error": str(e)}), 500

    @bp.route("/api/user/avatar", methods=["GET", "OPTIONS"])
    async def api_user_avatar():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            user_id = await _auth()
            if not user_id:
                return Response(status=401)
            token = os.getenv("TELEGRAM_TOKEN")
            if not token:
                return Response(status=500)
            from bot.db.users_db import get_user_by_id

            user = await get_user_by_id(user_id)
            if not user:
                return Response(status=404)
            tid = user.get("telegram_id")
            if not tid:
                return Response(status=404)
            base = f"https://api.telegram.org/bot{token}"
            photos_r = requests_lib.get(
                f"{base}/getUserProfilePhotos",
                params={"user_id": int(tid), "limit": 1},
                timeout=10,
            )
            if not photos_r.ok:
                logger.warning(
                    "getUserProfilePhotos: %s %s",
                    photos_r.status_code,
                    photos_r.text[:200],
                )
                return Response(status=502)
            data = photos_r.json()
            if not data.get("ok") or not data.get("result", {}).get("photos"):
                return Response(status=404)
            file_id = data["result"]["photos"][0][-1]["file_id"]
            file_r = requests_lib.get(f"{base}/getFile", params={"file_id": file_id}, timeout=10)
            if not file_r.ok:
                logger.warning("getFile: %s %s", file_r.status_code, file_r.text[:200])
                return Response(status=502)
            file_data = file_r.json()
            if not file_data.get("ok"):
                return Response(status=404)
            file_path = file_data["result"].get("file_path")
            if not file_path:
                return Response(status=404)
            r = requests_lib.get(
                f"https://api.telegram.org/file/bot{token}/{file_path}",
                timeout=10,
            )
            if not r.ok:
                return Response(status=502)
            return Response(
                r.content,
                mimetype="image/jpeg",
                headers={"Cache-Control": "private, max-age=3600"},
            )
        except Exception as e:
            logger.error("Ошибка /api/user/avatar: %s", e, exc_info=True)
            return Response(status=500)

    @bp.route("/api/user/change-password", methods=["POST", "OPTIONS"])
    async def api_user_change_password():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            user_id = await _auth()
            if not user_id:
                return jsonify({"error": "Требуется авторизация"}), 401
            data = await request.get_json(silent=True) or {}
            current = (data.get("current_password") or "").strip()
            new_pw = (data.get("new_password") or "").strip()
            if not current:
                return jsonify({"error": "Введите текущий пароль"}), 400
            ok, err = validate_password_format(new_pw)
            if not ok:
                return jsonify({"error": err}), 400
            from bot.db.users_db import get_user_by_id, update_user_password

            user = await get_user_by_id(user_id)
            if not user or not user.get("password_hash"):
                return jsonify({"error": "Пароль для этого аккаунта не настроен"}), 400
            if not check_password_hash(user["password_hash"], current):
                return jsonify({"error": "Неверный текущий пароль"}), 401
            if check_password_hash(user["password_hash"], new_pw):
                return jsonify({"error": "Новый пароль должен отличаться от текущего"}), 400
            new_hash = generate_password_hash(new_pw)
            await update_user_password(user_id, new_hash)
            return jsonify({"success": True, "message": "Пароль изменён"})
        except Exception as e:
            logger.error("Ошибка change-password: %s", e, exc_info=True)
            return jsonify({"error": str(e)}), 500

    @bp.route("/api/user/change-login", methods=["POST", "OPTIONS"])
    async def api_user_change_login():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            user_id = await _auth()
            if not user_id:
                return jsonify({"error": "Требуется авторизация"}), 401
            data = await request.get_json(silent=True) or {}
            current = (data.get("current_password") or "").strip()
            new_login = (data.get("new_login") or "").strip().lower()
            if not current:
                return jsonify({"error": "Введите текущий пароль"}), 400
            ok, err = validate_username_format(new_login)
            if not ok:
                return jsonify({"error": err}), 400
            from bot.db.users_db import (
                get_user_by_id,
                update_user_username,
                username_available,
            )

            user = await get_user_by_id(user_id)
            if not user or not user.get("password_hash"):
                return jsonify({"error": "Пароль для этого аккаунта не настроен"}), 400
            if not check_password_hash(user["password_hash"], current):
                return jsonify({"error": "Неверный текущий пароль"}), 401
            cur_username = (user.get("username") or "").strip().lower()
            if new_login == cur_username:
                return jsonify({"error": "Укажите новый логин, отличный от текущего"}), 400
            ok = await username_available(new_login, user_id)
            if not ok:
                return jsonify({"error": "Этот логин уже занят"}), 409
            await update_user_username(user_id, new_login)
            return jsonify({"success": True, "message": "Логин изменён", "username": new_login})
        except Exception as e:
            logger.error("Ошибка change-login: %s", e, exc_info=True)
            return jsonify({"error": str(e)}), 500

    @bp.route("/api/user/unlink-telegram", methods=["POST", "OPTIONS"])
    async def api_user_unlink_telegram():
        if request.method == "OPTIONS":
            return "", 200, CORS_HEADERS
        try:
            user_id = await _auth()
            if not user_id:
                return jsonify({"error": "Требуется авторизация"}), 401
            data = await request.get_json(silent=True) or {}
            current_password = (data.get("current_password") or "").strip()
            if not current_password:
                return jsonify({"error": "Введите текущий пароль"}), 400
            from bot.db.users_db import (
                get_user_by_id,
                update_user_telegram_id,
                delete_telegram_link,
                mark_telegram_id_known,
                rename_user_id,
                get_telegram_chat_id_for_notification,
            )

            user = await get_user_by_id(user_id)
            if not user:
                return jsonify({"error": "Пользователь не найден"}), 404
            if not user.get("password_hash"):
                return jsonify({
                    "error": "Для отвязки Telegram необходимо сначала настроить веб-доступ (логин и пароль)",
                }), 400
            if not check_password_hash(user["password_hash"], current_password):
                return jsonify({"error": "Неверный текущий пароль"}), 401
            telegram_id = user.get("telegram_id")
            if telegram_id is not None:
                telegram_id = str(telegram_id)
            if not telegram_id:
                _chat_id = await get_telegram_chat_id_for_notification(user_id)
                if _chat_id is not None:
                    telegram_id = str(_chat_id)
            # Старые tg_/numeric пользователи при отвязке переименовываются в web_username.
            # Новые usr_ пользователи не переименовываются — логин уже в users.username.
            is_legacy_tg_format = user_id.startswith("tg_") or user_id.isdigit()
            if not telegram_id:
                return jsonify({"error": "Telegram не привязан к этому аккаунту"}), 400
            if is_legacy_tg_format:
                username = user.get("username")
                if not username:
                    return jsonify({
                        "error": "Ошибка: у аккаунта нет логина для превращения в веб-аккаунт. Сначала смените логин.",
                    }), 400
                new_user_id = f"web_{username}"
                await rename_user_id(user_id, new_user_id)
                logger.info("Аккаунт %s превращен в %s при отвязке TG", user_id, new_user_id)
                user_id = new_user_id
            await delete_telegram_link(telegram_id)
            await mark_telegram_id_known(telegram_id)
            await update_user_telegram_id(user_id, None)
            logger.info(
                "Отвязан Telegram %s от аккаунта %s. Связь в telegram_links удалена.",
                telegram_id,
                user_id,
            )
            return jsonify({
                "success": True,
                "message": "Telegram успешно отвязан. Аккаунт переведен в режим веб-доступа.",
            })
        except Exception as e:
            logger.error("Ошибка unlink-telegram: %s", e, exc_info=True)
            return jsonify({"error": str(e)}), 500

    return bp
