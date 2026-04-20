"""
Quart Blueprint: POST /webhook/yookassa (YooKassa), POST /webhook/cryptocloud (CryptoCloud).
Async: respond 200 immediately, process payment in background task.

CryptoCloud: постбек приходит после подтверждения транзакции в блокчейне (обычно 30 сек – 10 мин;
BTC до часа). До этого в ЛК инвойс может быть «частично оплачен»; после подтверждения статус
меняется и мы получаем postback со status=success.
"""
import asyncio
import logging
import os

import jwt
from quart import Blueprint, request, jsonify

from daralla_backend.handlers.api_support.payment_processors import process_payment_webhook
from daralla_backend.services.payment_webhook_service import (
    normalize_cryptocloud_payload,
    parse_yookassa_webhook_payload,
    resolve_cryptocloud_postback_target,
)
from daralla_backend.web.observability import inc_metric

logger = logging.getLogger(__name__)

async def _cryptocloud_parse_postback_body():
    """JSON (рекомендуется в ЛК) или form-data — иначе get_json пустой и постбэк падал с 400."""
    json_payload = await request.get_json(silent=True)
    form_payload = None if json_payload else await request.form
    return normalize_cryptocloud_payload(json_payload, form_payload)


def create_blueprint(bot_app):
    bp = Blueprint("payment", __name__)

    async def _cryptocloud_postback():
        inc_metric("webhook_received_total", provider="cryptocloud")
        try:
            data = await _cryptocloud_parse_postback_body()
            if not data:
                inc_metric("webhook_failed_total", provider="cryptocloud", reason="empty_payload")
                return jsonify({"status": "error"}), 400
            # Документация: status, invoice_id (короткий id), invoice_info.uuid (INV-xxx), token (JWT HS256).
            status = (data.get("status") or "").strip().lower()
            target = await resolve_cryptocloud_postback_target(data)
            if not target:
                logger.warning("CryptoCloud postback: missing invoice uuid/invoice_id")
                return jsonify({"status": "ok"}), 200
            # Верификация JWT до обработки (документация: token подписан секретом проекта).
            secret = os.getenv("CRYPTOCLOUD_WEBHOOK_SECRET")
            token_str = data.get("token")
            if secret and token_str:
                try:
                    jwt.decode(token_str, secret, algorithms=["HS256"])
                except jwt.InvalidTokenError:
                    logger.warning("CryptoCloud postback: invalid JWT for raw_id=%s", target["raw_id"])
                    inc_metric("webhook_failed_total", provider="cryptocloud", reason="invalid_jwt")
                    return jsonify({"status": "error"}), 401
            elif not secret:
                logger.warning("CryptoCloud postback: CRYPTOCLOUD_WEBHOOK_SECRET not set")
            if not target["payment_found"]:
                logger.warning("CryptoCloud postback: payment not found for raw_id=%s", target["raw_id"])
            logger.info(
                "CryptoCloud postback: status=%s, raw_id=%s, payment_id=%s, found=%s",
                target["status"],
                target["raw_id"],
                target["payment_id"],
                target["payment_found"],
            )
            if target["payment_found"]:
                asyncio.create_task(_process_webhook(target["payment_id"], target["mapped_status"]))
                inc_metric("webhook_processed_total", provider="cryptocloud", status=target["mapped_status"])
            return jsonify({"status": "ok"}), 200
        except (TypeError, ValueError) as e:
            logger.warning("CryptoCloud webhook invalid payload: %s", e)
            inc_metric("webhook_failed_total", provider="cryptocloud", reason="invalid_payload")
            return jsonify({"status": "error"}), 400
        except Exception as e:
            logger.error("CryptoCloud webhook error: %s", e, exc_info=True)
            inc_metric("webhook_failed_total", provider="cryptocloud", reason="internal_error")
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
        inc_metric("webhook_received_total", provider="yookassa")
        try:
            data = await request.get_json(silent=True)
            logger.info("WEBHOOK: Получен webhook от YooKassa")
            logger.info("WEBHOOK: Данные: %s", data)
            logger.info("WEBHOOK: Заголовки: %s", dict(request.headers))

            try:
                resolved = parse_yookassa_webhook_payload(data)
            except ValueError as e:
                logger.error("Неверный формат webhook от YooKassa: %s", e)
                inc_metric("webhook_failed_total", provider="yookassa", reason="invalid_payload")
                return jsonify({"status": "error"}), 400

            if resolved is None:
                logger.info(
                    "WEBHOOK: событие %s — без обновления платежа",
                    (data.get("event") or "").strip(),
                )
                inc_metric("webhook_processed_total", provider="yookassa", status="ignored")
                return jsonify({"status": "ok"})

            payment_id, status = resolved
            event_name = (data.get("event") or "").strip()

            logger.info(
                "WEBHOOK: Обработка webhook: event=%s, payment_id=%s, status=%s",
                event_name or "(legacy)",
                payment_id,
                status,
            )
            if status == "succeeded":
                logger.info("WEBHOOK: Платеж успешен - активируем ключ")
            elif status == "canceled":
                logger.info("WEBHOOK: Платеж отменен - показываем ошибку")
            elif status == "refunded":
                logger.info("WEBHOOK: Платеж возвращен - показываем ошибку")
            else:
                logger.info("WEBHOOK: Неизвестный статус: %s", status)

            asyncio.create_task(_process_webhook(payment_id, status))
            inc_metric("webhook_processed_total", provider="yookassa", status=status)

            return jsonify({"status": "ok"})
        except (TypeError, ValueError) as e:
            logger.warning("YooKassa webhook invalid payload: %s", e)
            inc_metric("webhook_failed_total", provider="yookassa", reason="invalid_payload")
            return jsonify({"status": "error"}), 400
        except Exception as e:
            logger.error("Ошибка в webhook: %s", e, exc_info=True)
            inc_metric("webhook_failed_total", provider="yookassa", reason="internal_error")
            return jsonify({"status": "error"}), 500

    return bp


async def _process_webhook(payment_id, status):
    """Background task: run process_payment_webhook and log errors."""
    try:
        await process_payment_webhook(payment_id, status)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error("Ошибка обработки платежа в webhook: %s", e, exc_info=True)
