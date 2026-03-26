"""
Quart Blueprint: POST /webhook/yookassa (YooKassa), POST /webhook/cryptocloud (CryptoCloud).
Async: respond 200 immediately, process payment in background task.

CryptoCloud: постбек приходит после подтверждения транзакции в блокчейне (обычно 30 сек – 10 мин;
BTC до часа). До этого в ЛК инвойс может быть «частично оплачен»; после подтверждения статус
меняется и мы получаем postback со status=success.
"""
import asyncio
import hashlib
import hmac
import logging
import os
import time

import jwt
from quart import Blueprint, request, jsonify

from bot.db import (
    get_payment_by_id,
    begin_webhook_event,
    mark_webhook_event_done,
    mark_webhook_event_failed,
)
from bot.handlers.api_support.payment_processors import process_payment_webhook

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint("payment", __name__)

    def _replay_window_seconds() -> int:
        raw = os.getenv("WEBHOOK_REPLAY_WINDOW_SECONDS", "300")
        try:
            return max(30, int(raw))
        except ValueError:
            return 300

    def _timing_safe_hex(expected_hex: str, actual_hex: str) -> bool:
        try:
            return hmac.compare_digest(
                bytes.fromhex(expected_hex.lower()),
                bytes.fromhex((actual_hex or "").lower()),
            )
        except ValueError:
            return False

    def _verify_hmac_signature(raw_body: bytes, secret: str, signature: str) -> bool:
        expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        return _timing_safe_hex(expected, signature or "")

    def _verify_timestamp(ts_raw: str) -> bool:
        if not ts_raw:
            return False
        try:
            ts = int(ts_raw)
        except ValueError:
            return False
        return abs(int(time.time()) - ts) <= _replay_window_seconds()

    async def _run_idempotent(provider: str, payment_id: str, status: str):
        event_key = f"{provider}:{payment_id}:{status}"
        now_ts = int(time.time())
        should_process = await begin_webhook_event(event_key, provider, payment_id, status, now_ts)
        if not should_process:
            logger.info("Webhook duplicate skipped: %s", event_key)
            return
        try:
            await _process_webhook(bot_app, payment_id, status)
            await mark_webhook_event_done(event_key, int(time.time()))
        except Exception as e:
            await mark_webhook_event_failed(event_key, str(e), int(time.time()))
            raise

    async def _cryptocloud_postback():
        try:
            raw_body = await request.get_data()
            data = await request.get_json(silent=True)
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
            hmac_secret = os.getenv("CRYPTOCLOUD_HMAC_SECRET", "").strip()
            if hmac_secret:
                signature = request.headers.get("X-Cryptocloud-Signature") or request.headers.get("X-Signature")
                ts = request.headers.get("X-Cryptocloud-Timestamp") or request.headers.get("X-Timestamp")
                if not signature or not _verify_hmac_signature(raw_body, hmac_secret, signature):
                    logger.warning("CryptoCloud postback: invalid HMAC")
                    return jsonify({"status": "error"}), 401
                if not _verify_timestamp(ts):
                    logger.warning("CryptoCloud postback: replay window failed")
                    return jsonify({"status": "error"}), 401
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
                    asyncio.create_task(_run_idempotent("cryptocloud", payment_id, "succeeded"))
            else:
                our_status = "canceled" if status in ("cancelled", "canceled") else "failed"
                if info:
                    asyncio.create_task(_run_idempotent("cryptocloud", payment_id, our_status))
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
            raw_body = await request.get_data()
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

            yookassa_secret = os.getenv("YOOKASSA_WEBHOOK_SECRET", "").strip()
            if yookassa_secret:
                signature = request.headers.get("X-Yookassa-Signature") or request.headers.get("X-Signature")
                ts = request.headers.get("X-Yookassa-Timestamp") or request.headers.get("X-Timestamp")
                if not signature or not _verify_hmac_signature(raw_body, yookassa_secret, signature):
                    logger.warning("YooKassa webhook rejected: invalid signature")
                    return jsonify({"status": "error"}), 401
                if not _verify_timestamp(ts):
                    logger.warning("YooKassa webhook rejected: replay window failed")
                    return jsonify({"status": "error"}), 401

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
            asyncio.create_task(_run_idempotent("yookassa", payment_id, status))

            return jsonify({"status": "ok"})
        except (TypeError, ValueError) as e:
            logger.warning("YooKassa webhook invalid payload: %s", e)
            return jsonify({"status": "error"}), 400
        except Exception as e:
            logger.error("Ошибка в webhook: %s", e, exc_info=True)
            return jsonify({"status": "error"}), 500

    @bp.route("/webhook/remnawave", methods=["POST"])
    async def remnawave_webhook():
        try:
            raw_body = await request.get_data()
            secret = os.getenv("REMNAWAVE_WEBHOOK_SECRET_HEADER", "").strip()
            if secret:
                signature = request.headers.get("X-Remnawave-Signature", "")
                ts = request.headers.get("X-Remnawave-Timestamp", "")
                if not _verify_hmac_signature(raw_body, secret, signature):
                    logger.warning("RemnaWave webhook rejected: invalid signature")
                    return jsonify({"status": "error"}), 401
                if not _verify_timestamp(ts):
                    logger.warning("RemnaWave webhook rejected: replay window failed")
                    return jsonify({"status": "error"}), 401
            logger.info("RemnaWave webhook accepted")
            return jsonify({"status": "ok"}), 200
        except Exception as e:
            logger.error("RemnaWave webhook error: %s", e, exc_info=True)
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
