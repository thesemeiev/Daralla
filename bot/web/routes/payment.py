"""
Quart Blueprint: POST /webhook/yookassa (YooKassa webhook).
Async: respond 200 immediately, process payment in background task.
"""
import asyncio
import logging

from quart import Blueprint, request, jsonify

from bot.handlers.api_support.payment_processors import process_payment_webhook

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint("payment", __name__)

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
