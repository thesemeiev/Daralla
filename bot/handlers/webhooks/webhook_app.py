"""
Flask приложение для обработки webhook'ов от YooKassa
"""
import logging
import threading
import asyncio
from flask import Flask, request, jsonify

from .payment_processors import process_payment_webhook
from ...db.subscribers_db import get_subscription_by_token

logger = logging.getLogger(__name__)


def create_webhook_app(bot_app):
    """Создает Flask приложение для обработки webhook'ов от YooKassa"""
    app = Flask(__name__)
    
    @app.route('/webhook/yookassa', methods=['POST'])
    def yookassa_webhook():
        try:
            # Получаем данные от YooKassa
            data = request.get_json()
            logger.info(f"🔔 WEBHOOK: Получен webhook от YooKassa")
            logger.info(f"🔔 WEBHOOK: Данные: {data}")
            
            # Логируем заголовки для отладки
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
            
            # Логируем все возможные статусы
            if status == 'succeeded':
                logger.info(f" WEBHOOK:  Платеж успешен - активируем ключ")
            elif status == 'canceled':
                logger.info(f" WEBHOOK:  Платеж отменен - показываем ошибку")
            elif status == 'refunded':
                logger.info(f" WEBHOOK:  Платеж возвращен - показываем ошибку")
            else:
                logger.info(f" WEBHOOK:  Неизвестный статус: {status}")
            
            # Запускаем обработку платежа в отдельном потоке с изолированным event loop
            def process_payment():
                # Создаем новый event loop для этого потока
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    # Запускаем обработку платежа
                    loop.run_until_complete(process_payment_webhook(bot_app, payment_id, status))
                except Exception as e:
                    logger.error(f"Ошибка обработки платежа в webhook: {e}")
                finally:
                    # Закрываем event loop
                    try:
                        # Даем время на завершение всех операций
                        import time
                        time.sleep(1)
                        
                        # Отменяем все pending задачи
                        pending = asyncio.all_tasks(loop)
                        for task in pending:
                            task.cancel()
                        # Ждем завершения отмененных задач
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
    
    @app.route('/sub/<token>', methods=['GET'])
    def subscription(token):
        """
        Эндпоинт для получения VLESS ссылок подписки.
        Возвращает список VLESS ссылок для всех серверов в подписке.
        """
        # Обрабатываем OPTIONS запрос (CORS preflight)
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
        
        # Логируем входящий запрос
        logger.info(f"Входящий запрос subscription: token={token}, method={request.method}")
        
        try:
            # Получаем subscription_manager из bot_app
            def get_subscription_manager():
                """Получает subscription_manager из bot.py"""
                try:
                    from ... import bot as bot_module
                    return getattr(bot_module, 'subscription_manager', None)
                except (ImportError, AttributeError):
                    return None
            
            subscription_manager = get_subscription_manager()
            if not subscription_manager:
                logger.error("subscription_manager не доступен")
                return ("Service unavailable", 503)
            
            # Получаем подписку по токену
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                sub = loop.run_until_complete(get_subscription_by_token(token))
            finally:
                loop.close()
            
            if not sub:
                logger.warning(f"Подписка с токеном {token} не найдена")
                return ("Subscription not found", 404)
            
            # Логируем информацию о подписке для отладки
            logger.info(f"Запрос подписки: token={token}, subscription_id={sub['id']}, status={sub['status']}, expires_at={sub['expires_at']}")
            
            # Проверяем статус подписки
            if sub["status"] != "active":
                import datetime
                expires_str = datetime.datetime.fromtimestamp(sub["expires_at"]).strftime('%Y-%m-%d %H:%M:%S')
                error_msg = f"Subscription is not active (status: {sub['status']}, expires_at: {expires_str})"
                logger.warning(f"Подписка с токеном {token} не активна: {error_msg}")
                return (error_msg, 403)
            
            # Проверяем срок действия
            import time
            current_time = int(time.time())
            expires_at = sub["expires_at"]
            
            if expires_at < current_time:
                import datetime
                expires_str = datetime.datetime.fromtimestamp(expires_at).strftime('%Y-%m-%d %H:%M:%S')
                current_str = datetime.datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S')
                error_msg = f"Subscription expired (expired: {expires_str}, current: {current_str})"
                logger.warning(f"Подписка с токеном {token} истекла: {error_msg}")
                return (error_msg, 403)
            
            logger.info(f"Подписка {sub['id']} валидна, генерируем ссылки...")
            
            # Генерируем VLESS ссылки
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                links = loop.run_until_complete(
                    subscription_manager.build_vless_links_for_subscription(sub["id"])
                )
                logger.info(f"Сгенерировано {len(links)} VLESS ссылок для подписки {sub['id']}")
            except Exception as gen_e:
                logger.error(f"Ошибка при генерации VLESS ссылок для подписки {sub['id']}: {gen_e}", exc_info=True)
                return (f"Error generating links: {str(gen_e)}", 500)
            finally:
                loop.close()
            
            if not links:
                logger.warning(f"Не удалось сгенерировать ссылки для подписки {sub['id']} (пустой список)")
                # Получаем информацию о серверах для диагностики
                try:
                    from ...db.subscribers_db import get_subscription_servers
                    diag_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(diag_loop)
                    try:
                        servers = diag_loop.run_until_complete(get_subscription_servers(sub["id"]))
                        logger.warning(f"Серверов в подписке: {len(servers)}")
                        for s in servers:
                            logger.warning(f"  - {s['server_name']}: {s['client_email']}")
                    finally:
                        diag_loop.close()
                except Exception as e:
                    logger.error(f"Ошибка при получении информации о серверах: {e}")
                return ("No servers available", 503)
            
            # Получаем главное название VPN из bot.py для использования в ответе
            try:
                from ... import bot as bot_module
                vpn_brand_name = getattr(bot_module, 'VPN_BRAND_NAME', 'Daralla VPN')
            except (ImportError, AttributeError):
                vpn_brand_name = 'Daralla VPN'
            
            # Для клиента Happ нужно использовать специальный формат
            # Happ использует домен из URL подписки как название группы
            # Чтобы изменить название группы, нужно использовать заголовок new-domain или комментарий #new-domain
            # Извлекаем домен из названия (убираем эмодзи и пробелы, оставляем только буквы и цифры)
            import re
            # Убираем эмодзи и специальные символы, оставляем только буквы, цифры и пробелы
            clean_name = re.sub(r'[^\w\s-]', '', vpn_brand_name)
            # Заменяем пробелы на дефисы и приводим к нижнему регистру для домена
            domain_name = re.sub(r'\s+', '-', clean_name.strip()).lower()
            # Если название слишком длинное или содержит недопустимые символы, используем fallback
            if not domain_name or len(domain_name) > 63:  # Максимальная длина домена
                domain_name = 'daralla-vpn'
            
            # Возвращаем список VLESS ссылок в plain text формате
            # Каждая ссылка на новой строке - это стандартный формат для мультисерверных подписок
            # VPN клиенты (v2ray, clash, etc.) автоматически распознают этот формат
            # Для Happ добавляем несколько вариантов комментариев для автоматического определения названия
            # Попробуем разные форматы, которые могут поддерживаться Happ
            response_text = (
                f"#new-domain {domain_name}\n"
                f"# name: {vpn_brand_name}\n"
                f"#title: {vpn_brand_name}\n"
                + "\n".join(links) + "\n"
            )
            
            # Логируем первую ссылку для проверки tag
            if links:
                first_link = links[0]
                if '#' in first_link:
                    tag_part = first_link.split('#')[1]
                    logger.info(f"Проверка tag в первой ссылке: '{tag_part}' (URL-decoded)")
                else:
                    logger.warning(f"В первой ссылке отсутствует tag!")
            
            logger.info(f"Возвращаем {len(links)} VLESS ссылок для подписки {sub['id']} с названием группы: '{vpn_brand_name}'")
            
            # Формируем Subscription-UserInfo заголовок для указания названия группы
            # Многие VPN клиенты используют этот заголовок для отображения названия подписки
            import json
            import base64
            subscription_userinfo = {
                "upload": 0,
                "download": 0,
                "total": 0,
                "expire": sub["expires_at"],
                "remark": vpn_brand_name  # Название группы для VPN клиента
            }
            # Кодируем в base64 для заголовка
            userinfo_json = json.dumps(subscription_userinfo, ensure_ascii=False)
            userinfo_base64 = base64.b64encode(userinfo_json.encode('utf-8')).decode('utf-8')
            
            logger.info(f"Устанавливаем название группы подписки: '{vpn_brand_name}' (base64: {userinfo_base64[:50]}...)")
            logger.info(f"Устанавливаем домен для Happ клиента: '{domain_name}' (из '{vpn_brand_name}')")
            
            # Возвращаем как text/plain (стандартный Content-Type для subscription)
            # Добавляем CORS заголовки и Subscription-UserInfo для VPN клиентов
            # Для Happ пробуем разные варианты заголовков для автоматического определения названия
            # ВАЖНО: HTTP заголовки должны быть в ASCII/latin-1, без эмодзи!
            import urllib.parse
            # Убираем эмодзи из имени файла для Content-Disposition
            clean_filename = re.sub(r'[^\w\s-]', '', vpn_brand_name).strip().replace(' ', '-').lower()
            if not clean_filename:
                clean_filename = 'daralla-vpn'
            
            # Убираем эмодзи из названия для заголовков (только ASCII)
            clean_name_for_header = re.sub(r'[^\w\s-]', '', vpn_brand_name).strip()
            if not clean_name_for_header:
                clean_name_for_header = 'Daralla VPN'
            
            headers = {
                "Content-Type": "text/plain; charset=utf-8",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "*",
                "Subscription-UserInfo": userinfo_base64,  # Заголовок с информацией о подписке (включая название группы)
                "Content-Disposition": f'attachment; filename="{clean_filename}"',  # Имя файла для Happ (attachment вместо inline)
                "new-domain": domain_name,  # Заголовок для Happ VPN клиента (определяет название группы вместо домена из URL)
                "X-Subscription-Name": clean_name_for_header,  # Дополнительный заголовок с названием (БЕЗ эмодзи, только ASCII)
            }
            return (response_text, 200, headers)
            
        except Exception as e:
            logger.error(f"Ошибка в эндпоинте /sub/<token>: {e}")
            return ("Internal server error", 500)
    
    return app

