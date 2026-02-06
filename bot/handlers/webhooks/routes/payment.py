"""
Blueprint: POST /webhook/yookassa (YooKassa webhook).
Использует webhook_utils.run_async() для управления asyncio вthread контексте.
"""
import asyncio
import logging
from flask import Blueprint, request, jsonify, current_app

from ..payment_processors import process_payment_webhook
from ..webhook_utils import run_async

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint('payment', __name__)

    @bp.route('/webhook/yookassa', methods=['POST'])
    def yookassa_webhook():
        try:
            data = request.get_json()
            logger.info("🔔 WEBHOOK: Получен webhook от YooKassa")
            logger.info(f"🔔 WEBHOOK: Данные: {data}")

            if not data or 'object' not in data:
                logger.error("Неверный формат webhook от YooKassa")
                return jsonify({'status': 'error'}), 400

            payment_data = data['object']
            payment_id = payment_data.get('id')
            status = payment_data.get('status')

            if not payment_id or not status:
                logger.error("Отсутствуют обязательные поля в webhook")
                return jsonify({'status': 'error'}), 400

            logger.info(f"WEBHOOK: Обработка payment_id={payment_id}, status={status}")

            # Попытка запланировать обработку в основном asyncio loop приложения
            app_ctx = None
            try:
                app_ctx = current_app.config.get("BOT_CONTEXT")
            except RuntimeError:
                app_ctx = None
            
            main_loop = getattr(app_ctx, "main_loop", None) if app_ctx is not None else None
            
            if main_loop and hasattr(asyncio, "run_coroutine_threadsafe"):
                # Используем основной loop приложения если доступен
                fut = asyncio.run_coroutine_threadsafe(
                    process_payment_webhook(bot_app, payment_id, status), main_loop
                )
                def _on_done(f):
                    try:
                        exc = f.exception()
                        if exc:
                            logger.error("Ошибка обработки платежа: %s", exc)
                    except Exception:
                        pass
                fut.add_done_callback(_on_done)
            else:
                # Fallback: используем run_async() для создания нового loop
                async def process_async():
                    await process_payment_webhook(bot_app, payment_id, status)
                
                try:
                    run_async(process_async())
                except Exception as e:
                    logger.error(f"Ошибка обработки платежа: {e}")

            return jsonify({'status': 'ok'})

        except Exception as e:
            logger.error(f"Ошибка в webhook: {e}")
            return jsonify({'status': 'error'}), 500

    return bp
