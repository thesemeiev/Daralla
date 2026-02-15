"""
Quart Blueprint: POST /webhook/yookassa (YooKassa), POST /webhook/cryptocloud (CryptoCloud).
Async: respond 200 immediately, process payment in background task.
"""
import asyncio
import logging
import os

import jwt
from quart import Blueprint, request, jsonify

from bot.handlers.api_support.payment_processors import process_payment_webhook

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint("payment", __name__)

    async def _cryptocloud_postback():
        try:
            data = await request.get_json(silent=True)
            if not data:
                return jsonify({"status": "error"}), 400
            token_str = data.get("token")
            status = (data.get("status") or "").strip().lower()
            invoice_info = data.get("invoice_info") or {}
            invoice_uuid = invoice_info.get("uuid") or data.get("invoice_id")
            if not invoice_uuid:
                logger.warning("CryptoCloud postback: missing invoice uuid/invoice_id")
                return jsonify({"status": "ok"}), 200
            secret = os.getenv("CRYPTOCLOUD_WEBHOOK_SECRET")
            if secret and token_str:
                try:
                    jwt.decode(token_str, secret, algorithms=["HS256"])
                except jwt.InvalidTokenError:
                    logger.warning("CryptoCloud postback: invalid JWT for uuid=%s", invoice_uuid)
                    return jsonify({"status": "error"}), 401
            elif not secret:
                logger.warning("CryptoCloud postback: CRYPTOCLOUD_WEBHOOK_SECRET not set")
            # Успех — активируем подписку; отмена/истечение/ошибка — обновляем статус в БД, фронт сразу покажет сообщение
            if status == "success":
                asyncio.create_task(_process_webhook(bot_app, invoice_uuid, "succeeded"))
            else:
                # cancelled, expired, failed или любой не success — помечаем как неуспех
                our_status = "canceled" if status in ("cancelled", "canceled") else "failed"
                asyncio.create_task(_process_webhook(bot_app, invoice_uuid, our_status))
            return jsonify({"status": "ok"}), 200
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
            data = await request.get_json()
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

        except Exception as e:
            logger.error("Ошибка в webhook: %s", e, exc_info=True)
            return jsonify({"status": "error"}), 500

    return bp


async def _process_webhook(bot_app, payment_id, status):
    """Background task: run process_payment_webhook and log errors."""
    try:
        await process_payment_webhook(bot_app, payment_id, status)
    except Exception as e:
        logger.error("Ошибка обработки платежа в webhook: %s", e, exc_info=True)
