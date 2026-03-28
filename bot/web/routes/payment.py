"""
Quart Blueprint: POST /webhook/yookassa (YooKassa), POST /webhook/cryptocloud (CryptoCloud).
Async: respond 200 immediately, process payment in background task.

CryptoCloud: постбек приходит после подтверждения транзакции в блокчейне (обычно 30 сек – 10 мин;
BTC до часа). До этого в ЛК инвойс может быть «частично оплачен»; после подтверждения статус
меняется и мы получаем postback со status=success.
"""
import asyncio
import json
import logging
import os

import jwt
from quart import Blueprint, request, jsonify

from bot.db import get_payment_by_id
from bot.handlers.api_support.payment_processors import process_payment_webhook

logger = logging.getLogger(__name__)


async def _cryptocloud_parse_postback_body():
    """JSON (рекомендуется в ЛК) или form-data — иначе get_json пустой и постбэк падал с 400."""
    data = await request.get_json(silent=True)
    if data:
        return data
    form = await request.form
    if not form:
        return None
    flat = form.to_dict()
    inv = flat.get("invoice_info")
    if isinstance(inv, str) and inv.strip().startswith("{"):
        try:
            flat["invoice_info"] = json.loads(inv)
        except (json.JSONDecodeError, TypeError):
            flat["invoice_info"] = {}
    elif "invoice_info" not in flat:
        flat["invoice_info"] = {}
    return flat


def create_blueprint(bot_app):
    bp = Blueprint("payment", __name__)

    async def _cryptocloud_postback():
        try:
            data = await _cryptocloud_parse_postback_body()
            if not data:
                return jsonify({"status": "error"}), 400
            # Документация: status, invoice_id (короткий id), invoice_info.uuid (INV-xxx), token (JWT HS256).
            status = (data.get("status") or "").strip().lower()
            invoice_info = data.get("invoice_info") or {}
            raw_id = invoice_info.get("uuid") or data.get("invoice_id")
            if not raw_id:
                logger.warning("CryptoCloud postback: missing invoice uuid/invoice_id")
                return jsonify({"status": "ok"}), 200
            # Верификация JWT до обработки (документация: token подписан секретом проекта).
            secret = os.getenv("CRYPTOCLOUD_WEBHOOK_SECRET")
            token_str = data.get("token")
            if secret and token_str:
                try:
                    jwt.decode(token_str, secret, algorithms=["HS256"])
                except jwt.InvalidTokenError:
                    logger.warning("CryptoCloud postback: invalid JWT for raw_id=%s", raw_id)
                    return jsonify({"status": "error"}), 401
            elif not secret:
                logger.warning("CryptoCloud postback: CRYPTOCLOUD_WEBHOOK_SECRET not set")
            # В create сохраняем payment_id = result["uuid"] (INV-XXXXXXXX). В постбеке приходит
            # invoice_info.uuid (INV-xxx) или invoice_id (короткий). Ищем в БД; при коротком id пробуем INV- + id.
            payment_id = raw_id
            info = await get_payment_by_id(raw_id)
            if not info and not str(raw_id).strip().upper().startswith("INV-"):
                payment_id = "INV-" + str(raw_id).strip()
                info = await get_payment_by_id(payment_id)
            if info:
                payment_id = info["payment_id"]
            else:
                logger.warning("CryptoCloud postback: payment not found for raw_id=%s", raw_id)
            logger.info("CryptoCloud postback: status=%s, raw_id=%s, payment_id=%s, found=%s", status, raw_id, payment_id, bool(info))
            if status == "success":
                if info:
                    asyncio.create_task(_process_webhook(bot_app, payment_id, "succeeded"))
            else:
                our_status = "canceled" if status in ("cancelled", "canceled") else "failed"
                if info:
                    asyncio.create_task(_process_webhook(bot_app, payment_id, our_status))
            return jsonify({"status": "ok"}), 200
        except (TypeError, ValueError) as e:
            logger.warning("CryptoCloud webhook invalid payload: %s", e)
            return jsonify({"status": "error"}), 400
        except Exception as e:
            logger.error("CryptoCloud webhook error: %s", e, exc_info=True)
            return jsonify({"status": "error"}), 500

    @bp.route("/webhook/cryptocloud", methods=["POST"])
    async def cryptocloud_webhook():
        return await _cryptocloud_postback()

    @bp.route("/callback", methods=["POST"])
    async def cryptocloud_callback():
        """Тот же постбэк CryptoCloud — для случая, когда в ЛК указан URL https://daralla.ru/callback."""
        return await _cryptocloud_postback()

    @bp.route("/webhook/yookassa", methods=["POST"])
    async def yookassa_webhook():
        try:
            data = await request.get_json(silent=True)
            logger.info("WEBHOOK: Получен webhook от YooKassa")
            logger.info("WEBHOOK: Данные: %s", data)
            logger.info("WEBHOOK: Заголовки: %s", dict(request.headers))

            if not data or "object" not in data:
                logger.error("Неверный формат webhook от YooKassa")
                return jsonify({"status": "error"}), 400

            payment_data = data["object"]
            payment_id = payment_data.get("id")
            status = payment_data.get("status")

            if not payment_id or not status:
                logger.error("Отсутствуют обязательные поля в webhook")
                return jsonify({"status": "error"}), 400

            logger.info("WEBHOOK: Обработка webhook: payment_id=%s, status=%s", payment_id, status)
            if status == "succeeded":
                logger.info("WEBHOOK: Платеж успешен - активируем ключ")
            elif status == "canceled":
                logger.info("WEBHOOK: Платеж отменен - показываем ошибку")
            elif status == "refunded":
                logger.info("WEBHOOK: Платеж возвращен - показываем ошибку")
            else:
                logger.info("WEBHOOK: Неизвестный статус: %s", status)

            # Обработка в фоне, чтобы сразу вернуть 200 YooKassa
            asyncio.create_task(_process_webhook(bot_app, payment_id, status))

            return jsonify({"status": "ok"})
        except (TypeError, ValueError) as e:
            logger.warning("YooKassa webhook invalid payload: %s", e)
            return jsonify({"status": "error"}), 400
        except Exception as e:
            logger.error("Ошибка в webhook: %s", e, exc_info=True)
            return jsonify({"status": "error"}), 500

    return bp


async def _process_webhook(bot_app, payment_id, status):
    """Background task: run process_payment_webhook and log errors."""
    try:
        await process_payment_webhook(bot_app, payment_id, status)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error("Ошибка обработки платежа в webhook: %s", e, exc_info=True)
