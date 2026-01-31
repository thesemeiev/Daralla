"""
Blueprint: POST /webhook/yookassa (YooKassa webhook).
"""
import asyncio
import logging
import threading
from flask import Blueprint, request, jsonify

from ..payment_processors import process_payment_webhook

logger = logging.getLogger(__name__)


def create_blueprint(bot_app):
    bp = Blueprint('payment', __name__)

    @bp.route('/webhook/yookassa', methods=['POST'])
    def yookassa_webhook():
        try:
            data = request.get_json()
            logger.info("🔔 WEBHOOK: Получен webhook от YooKassa")
            logger.info(f"🔔 WEBHOOK: Данные: {data}")
            logger.info(f"🔔 WEBHOOK: Заголовки: {dict(request.headers)}")

            if not data or 'object' not in data:
                logger.error("Неверный формат webhook от YooKassa")
                return jsonify({'status': 'error'}), 400

            payment_data = data['object']
            payment_id = payment_data.get('id')
            status = payment_data.get('status')

            if not payment_id or not status:
                logger.error("Отсутствуют обязательные поля в webhook")
                return jsonify({'status': 'error'}), 400

            logger.info(f" WEBHOOK: Обработка webhook: payment_id={payment_id}, status={status}")
            if status == 'succeeded':
                logger.info(" WEBHOOK:  Платеж успешен - активируем ключ")
            elif status == 'canceled':
                logger.info(" WEBHOOK:  Платеж отменен - показываем ошибку")
            elif status == 'refunded':
                logger.info(" WEBHOOK:  Платеж возвращен - показываем ошибку")
            else:
                logger.info(f" WEBHOOK:  Неизвестный статус: {status}")

            def process_payment():
                import time
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(process_payment_webhook(bot_app, payment_id, status))
                except Exception as e:
                    logger.error(f"Ошибка обработки платежа в webhook: {e}")
                finally:
                    try:
                        time.sleep(1)
                        pending = asyncio.all_tasks(loop)
                        for task in pending:
                            task.cancel()
                        if pending:
                            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                    except Exception as e:
                        logger.warning(f"Ошибка при закрытии event loop: {e}")
                    finally:
                        loop.close()

            thread = threading.Thread(target=process_payment, daemon=True)
            thread.start()

            return jsonify({'status': 'ok'})

        except Exception as e:
            logger.error(f"Ошибка в webhook: {e}")
            return jsonify({'status': 'error'}), 500

    return bp
