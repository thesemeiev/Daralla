"""
Quart Blueprint: POST /webhook/yookassa (YooKassa), POST /webhook/cryptocloud (CryptoCloud),
POST /webhook/platega (Platega).
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
    parse_platega_webhook_payload,
    parse_yookassa_webhook_payload,
    resolve_platega_postback_target,
    resolve_cryptocloud_postback_target,
    verify_platega_webhook_headers,
)
from daralla_backend.utils.logging_helpers import log_event, sanitize_headers
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
                log_event(
                    logger,
                    logging.WARNING,
                    "cryptocloud_postback_missing_target",
                    path=request.path,
                )
                return jsonify({"status": "ok"}), 200
            # Верификация JWT до обработки (документация: token подписан секретом проекта).
            secret = os.getenv("CRYPTOCLOUD_WEBHOOK_SECRET")
            token_str = data.get("token")
            if secret and token_str:
                try:
                    jwt.decode(token_str, secret, algorithms=["HS256"])
                except jwt.InvalidTokenError:
                    log_event(
                        logger,
                        logging.WARNING,
                        "cryptocloud_postback_invalid_jwt",
                        raw_id=target["raw_id"],
                    )
                    inc_metric("webhook_failed_total", provider="cryptocloud", reason="invalid_jwt")
                    return jsonify({"status": "error"}), 401
            elif not secret:
                log_event(
                    logger,
                    logging.WARNING,
                    "cryptocloud_webhook_secret_missing",
                )
            if not target["payment_found"]:
                log_event(
                    logger,
                    logging.WARNING,
                    "cryptocloud_postback_payment_not_found",
                    raw_id=target["raw_id"],
                )
            log_event(
                logger,
                logging.INFO,
                "cryptocloud_postback_received",
                provider="cryptocloud",
                status=target["status"],
                raw_id=target["raw_id"],
                payment_id=target["payment_id"],
                payment_found=target["payment_found"],
                path=request.path,
            )
            if target["payment_found"]:
                asyncio.create_task(_process_webhook(target["payment_id"], target["mapped_status"]))
                inc_metric("webhook_processed_total", provider="cryptocloud", status=target["mapped_status"])
            return jsonify({"status": "ok"}), 200
        except (TypeError, ValueError) as e:
            log_event(
                logger,
                logging.WARNING,
                "cryptocloud_webhook_invalid_payload",
                error=str(e),
                path=request.path,
            )
            inc_metric("webhook_failed_total", provider="cryptocloud", reason="invalid_payload")
            return jsonify({"status": "error"}), 400
        except Exception as e:
            log_event(
                logger,
                logging.ERROR,
                "cryptocloud_webhook_internal_error",
                error=str(e),
                path=request.path,
            )
            logger.debug("cryptocloud_webhook_internal_error_traceback", exc_info=True)
            inc_metric("webhook_failed_total", provider="cryptocloud", reason="internal_error")
            return jsonify({"status": "error"}), 500

    @bp.route("/webhook/cryptocloud", methods=["POST"])
    async def cryptocloud_webhook():
        return await _cryptocloud_postback()

    @bp.route("/callback", methods=["POST"])
    async def cryptocloud_callback():
        """Тот же постбэк CryptoCloud — для случая, когда в ЛК указан URL https://daralla.ru/callback."""
        return await _cryptocloud_postback()

    @bp.route("/webhook/platega", methods=["POST"])
    async def platega_webhook():
        inc_metric("webhook_received_total", provider="platega")
        try:
            data = await request.get_json(silent=True)
            normalized = parse_platega_webhook_payload(data)
            target = await resolve_platega_postback_target(normalized)
            if not target:
                log_event(
                    logger,
                    logging.WARNING,
                    "platega_postback_missing_target",
                    path=request.path,
                )
                return jsonify({"status": "ok"}), 200

            merchant_id = (os.getenv("PLATEGA_MERCHANT_ID") or "").strip()
            secret = (os.getenv("PLATEGA_SECRET") or "").strip()
            if not merchant_id or not secret:
                log_event(
                    logger,
                    logging.WARNING,
                    "platega_webhook_secret_missing",
                )
                inc_metric("webhook_failed_total", provider="platega", reason="config_missing")
                return jsonify({"status": "error"}), 503

            if not verify_platega_webhook_headers(request.headers, merchant_id, secret):
                log_event(
                    logger,
                    logging.WARNING,
                    "platega_postback_invalid_headers",
                    raw_id=target["raw_id"],
                )
                inc_metric("webhook_failed_total", provider="platega", reason="invalid_headers")
                return jsonify({"status": "error"}), 401

            if not target["payment_found"]:
                log_event(
                    logger,
                    logging.WARNING,
                    "platega_postback_payment_not_found",
                    raw_id=target["raw_id"],
                )
            log_event(
                logger,
                logging.INFO,
                "platega_postback_received",
                provider="platega",
                status=target["status"],
                raw_id=target["raw_id"],
                payment_id=target["payment_id"],
                payment_found=target["payment_found"],
                path=request.path,
            )
            if target["payment_found"]:
                asyncio.create_task(_process_webhook(target["payment_id"], target["mapped_status"]))
                inc_metric("webhook_processed_total", provider="platega", status=target["mapped_status"])
            return jsonify({"status": "ok"}), 200
        except (TypeError, ValueError) as e:
            log_event(
                logger,
                logging.WARNING,
                "platega_webhook_invalid_payload",
                error=str(e),
                path=request.path,
            )
            inc_metric("webhook_failed_total", provider="platega", reason="invalid_payload")
            return jsonify({"status": "error"}), 400
        except Exception as e:
            log_event(
                logger,
                logging.ERROR,
                "platega_webhook_internal_error",
                error=str(e),
                path=request.path,
            )
            logger.debug("platega_webhook_internal_error_traceback", exc_info=True)
            inc_metric("webhook_failed_total", provider="platega", reason="internal_error")
            return jsonify({"status": "error"}), 500

    @bp.route("/webhook/yookassa", methods=["POST"])
    async def yookassa_webhook():
        inc_metric("webhook_received_total", provider="yookassa")
        try:
            data = await request.get_json(silent=True)
            event_name_raw = ((data or {}).get("event") or "").strip()
            object_payload = (data or {}).get("object") or {}
            log_event(
                logger,
                logging.INFO,
                "yookassa_webhook_received",
                provider="yookassa",
                provider_event=event_name_raw or "unknown",
                object_id=object_payload.get("id"),
                object_status=object_payload.get("status"),
                path=request.path,
                headers=sanitize_headers(dict(request.headers)),
            )

            try:
                resolved = parse_yookassa_webhook_payload(data)
            except ValueError as e:
                log_event(
                    logger,
                    logging.WARNING,
                    "yookassa_webhook_invalid_payload",
                    error=str(e),
                    provider_event=event_name_raw or "unknown",
                )
                inc_metric("webhook_failed_total", provider="yookassa", reason="invalid_payload")
                return jsonify({"status": "error"}), 400

            if resolved is None:
                log_event(
                    logger,
                    logging.INFO,
                    "yookassa_webhook_ignored_event",
                    provider_event=event_name_raw or "unknown",
                )
                inc_metric("webhook_processed_total", provider="yookassa", status="ignored")
                return jsonify({"status": "ok"})

            payment_id, status = resolved
            event_name = event_name_raw

            log_event(
                logger,
                logging.INFO,
                "yookassa_webhook_processed",
                provider_event=event_name or "legacy",
                payment_id=payment_id,
                status=status,
            )

            asyncio.create_task(_process_webhook(payment_id, status))
            inc_metric("webhook_processed_total", provider="yookassa", status=status)

            return jsonify({"status": "ok"})
        except (TypeError, ValueError) as e:
            log_event(
                logger,
                logging.WARNING,
                "yookassa_webhook_invalid_payload",
                error=str(e),
                path=request.path,
            )
            inc_metric("webhook_failed_total", provider="yookassa", reason="invalid_payload")
            return jsonify({"status": "error"}), 400
        except Exception as e:
            log_event(
                logger,
                logging.ERROR,
                "yookassa_webhook_internal_error",
                error=str(e),
                path=request.path,
            )
            logger.debug("yookassa_webhook_internal_error_traceback", exc_info=True)
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
        log_event(
            logger,
            logging.ERROR,
            "payment_webhook_processing_failed",
            payment_id=payment_id,
            status=status,
            error=str(e),
        )
        logger.debug("payment_webhook_processing_failed_traceback", exc_info=True)
