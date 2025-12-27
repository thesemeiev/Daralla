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
        # Определяем тип клиента по User-Agent (если возможно)
        # Многие VPN клиенты не отправляют User-Agent, поэтому определение может быть ненадежным
        user_agent = request.headers.get('User-Agent', '').lower()
        x_client = request.headers.get('X-Client', '').lower()
        is_happ_client = 'happ' in user_agent or 'happ' in x_client
        is_v2raytun_client = 'v2raytun' in user_agent or 'v2raytun' in x_client
        
        # Логируем для отладки
        if user_agent or x_client:
            logger.debug(f"Определение клиента: User-Agent='{user_agent[:100]}', X-Client='{x_client}', is_happ={is_happ_client}, is_v2raytun={is_v2raytun_client}")
        
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
            
            # Генерируем VLESS ссылки и получаем информацию о серверах
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                links = loop.run_until_complete(
                    subscription_manager.build_vless_links_for_subscription(sub["id"])
                )
                logger.info(f"Сгенерировано {len(links)} VLESS ссылок для подписки {sub['id']}")
                
                # Получаем список серверов для статистики трафика
                from ...db.subscribers_db import get_subscription_servers
                servers = loop.run_until_complete(get_subscription_servers(sub["id"]))
            except Exception as gen_e:
                logger.error(f"Ошибка при генерации VLESS ссылок для подписки {sub['id']}: {gen_e}", exc_info=True)
                return (f"Error generating links: {str(gen_e)}", 500)
            finally:
                # НЕ закрываем loop здесь, он понадобится для получения статистики трафика
                pass
            
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
            
            # Получаем ссылки на сайт и Telegram из переменных окружения (если установлены)
            import os
            website_url = os.getenv("WEBSITE_URL", "").strip()
            telegram_url = os.getenv("TELEGRAM_URL", "").strip()
            
            # Определяем время истечения (в секундах и миллисекундах)
            expire_timestamp_seconds = sub["expires_at"]  # Unix timestamp в секундах
            expire_timestamp_ms = expire_timestamp_seconds * 1000  # В миллисекундах
            
            # Получаем статистику трафика со всех серверов подписки ПЕРЕД формированием ответа
            # Суммируем upload, download и total со всех серверов
            total_upload = 0
            total_download = 0
            total_traffic = 0
            
            logger.info(f"Начало получения статистики трафика для подписки {sub['id']} с {len(servers)} серверами")
            
            try:
                # Получаем server_manager для доступа к XUI объектам
                def get_server_manager():
                    """Получает server_manager из bot.py"""
                    try:
                        from ... import bot as bot_module
                        return getattr(bot_module, 'server_manager', None)
                    except (ImportError, AttributeError):
                        return None
                
                server_manager = get_server_manager()
                if server_manager and servers:
                    for s in servers:
                        server_name = s["server_name"]
                        client_email = s["client_email"]
                        
                        try:
                            xui, resolved_name = server_manager.get_server_by_name(server_name)
                            if xui:
                                # Получаем статистику трафика клиента с этого сервера
                                traffic_stats = xui.get_client_traffic(client_email)
                                if traffic_stats:
                                    total_upload += traffic_stats.get("upload", 0)
                                    total_download += traffic_stats.get("download", 0)
                                    # Для total берем максимальное значение (если лимиты разные на серверах)
                                    total_traffic = max(total_traffic, traffic_stats.get("total", 0))
                                    logger.debug(f"Статистика трафика для {client_email} на {server_name}: upload={traffic_stats.get('upload', 0)}, download={traffic_stats.get('download', 0)}, total={traffic_stats.get('total', 0)}")
                        except Exception as e:
                            logger.warning(f"Не удалось получить статистику трафика для {client_email} на {server_name}: {e}")
                            # Продолжаем с другими серверами
                            continue
                
                logger.info(f"Общая статистика трафика подписки: upload={total_upload}, download={total_download}, total={total_traffic}")
            except Exception as e:
                logger.warning(f"Ошибка получения статистики трафика: {e}, используем значения по умолчанию")
            finally:
                # Закрываем loop после получения статистики
                loop.close()
            
            # Теперь формируем ответ с комментариями (после получения статистики трафика)
            # Возвращаем список VLESS ссылок в plain text формате
            # Каждая ссылка на новой строке - это стандартный формат для мультисерверных подписок
            # VPN клиенты (v2ray, clash, etc.) автоматически распознают этот формат
            # Для Happ добавляем несколько вариантов комментариев для автоматического определения названия
            # Также добавляем ссылки на сайт и Telegram для некоторых клиентов
            response_lines = []
            
            # Добавляем комментарии с названием
            response_lines.append(f"#new-domain {domain_name}")
            response_lines.append(f"# name: {vpn_brand_name}")
            response_lines.append(f"#title: {vpn_brand_name}")
            
            # Добавляем информацию о времени истечения в комментариях
            # Некоторые клиенты могут читать эту информацию из комментариев
            import datetime
            expire_datetime = datetime.datetime.fromtimestamp(expire_timestamp_seconds)
            expire_str = expire_datetime.strftime('%Y-%m-%d %H:%M:%S')
            response_lines.append(f"#expire: {expire_timestamp_seconds}")  # В секундах
            response_lines.append(f"#expiryTime: {expire_timestamp_ms}")  # В миллисекундах
            response_lines.append(f"#expire-date: {expire_str}")  # Человекочитаемый формат
            
            # Добавляем информацию о трафике в комментариях
            # Форматируем трафик в читаемый вид (ГБ, МБ)
            def format_bytes(bytes_value):
                """Форматирует байты в читаемый формат"""
                if bytes_value == 0:
                    return "0 B"
                for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
                    if bytes_value < 1024.0:
                        return f"{bytes_value:.2f} {unit}"
                    bytes_value /= 1024.0
                return f"{bytes_value:.2f} PB"
            
            total_used = total_upload + total_download
            response_lines.append(f"#upload: {total_upload}")  # В байтах
            response_lines.append(f"#download: {total_download}")  # В байтах
            response_lines.append(f"#total: {total_traffic if total_traffic > 0 else 0}")  # Лимит в байтах
            response_lines.append(f"#used: {total_used}")  # Использовано в байтах
            response_lines.append(f"#upload-formatted: {format_bytes(total_upload)}")
            response_lines.append(f"#download-formatted: {format_bytes(total_download)}")
            response_lines.append(f"#total-formatted: {format_bytes(total_traffic) if total_traffic > 0 else 'Unlimited'}")
            response_lines.append(f"#used-formatted: {format_bytes(total_used)}")
            
            # Подготавливаем данные для Happ VPN перед формированием комментариев
            # Формат subscription-userinfo для Happ (строка с разделителями)
            subscription_userinfo_happ = (
                f"upload={total_upload}; "
                f"download={total_download}; "
                f"total={total_traffic if total_traffic > 0 else 0}; "
                f"expire={expire_timestamp_seconds}"
            )
            
            # Подготавливаем clean_name_for_header для profile-title (максимум 25 символов)
            import re
            clean_name_for_header = re.sub(r'[^\w\s-]', '', vpn_brand_name).strip()
            if not clean_name_for_header:
                clean_name_for_header = 'Daralla VPN'
            # Happ требует максимум 25 символов для profile-title
            if len(clean_name_for_header) > 25:
                clean_name_for_header = clean_name_for_header[:25]
                logger.warning(f"profile-title обрезан до 25 символов: '{clean_name_for_header}'")
            
            # Добавляем ссылки на сайт и Telegram (если установлены)
            # Формат для Happ VPN согласно официальной документации
            if website_url:
                response_lines.append(f"#profile-web-page-url: {website_url}")  # Кнопка сайта для Happ (левая иконка)
                response_lines.append(f"#website: {website_url}")  # Для других клиентов
                response_lines.append(f"#support-url: {website_url}")  # Для других клиентов
            if telegram_url:
                response_lines.append(f"#support-url: {telegram_url}")  # Кнопка поддержки для Happ (правая иконка, если ведет в Telegram - показывается иконка Telegram)
                response_lines.append(f"#telegram: {telegram_url}")  # Для других клиентов
                response_lines.append(f"#telegram-url: {telegram_url}")  # Для других клиентов
                response_lines.append(f"#tg: {telegram_url}")  # Для других клиентов
            
            # Добавляем subscription-userinfo в формате Happ в комментариях
            response_lines.append(f"#subscription-userinfo: {subscription_userinfo_happ}")
            
            # Добавляем profile-title и profile-update-interval для Happ и V2RayTun
            response_lines.append(f"#profile-title: {clean_name_for_header}")
            response_lines.append(f"#profile-update-interval: 1")
            
            # НЕ добавляем announce в комментариях, чтобы Happ не показывал его
            # Happ читает announce из комментариев, что вызывает несостыковки с кнопками
            # V2RayTun будет получать announce через HTTP заголовки (добавляется ниже)
            # Это обеспечивает единообразное оформление: Happ использует кнопки, V2RayTun использует announce
            if telegram_url and is_happ_client:
                logger.debug(f"Пропущен announce в комментариях для Happ клиента (используются кнопки через заголовки)")
            
            # Добавляем VLESS ссылки
            response_lines.extend(links)
            
            response_text = "\n".join(response_lines) + "\n"
            
            # Логируем первую ссылку для проверки tag
            if links:
                first_link = links[0]
                if '#' in first_link:
                    tag_part = first_link.split('#')[1]
                    logger.info(f"Проверка tag в первой ссылке: '{tag_part}' (URL-decoded)")
                else:
                    logger.warning(f"В первой ссылке отсутствует tag!")
            
            logger.info(f"Возвращаем {len(links)} VLESS ссылок для подписки {sub['id']} с названием группы: '{vpn_brand_name}'")
            logger.info(f"Статистика трафика в ответе: upload={total_upload}, download={total_download}, total={total_traffic}, expire={expire_timestamp_seconds}")
            
            # Логируем содержимое subscription-userinfo для отладки
            # Используем строковый формат для совместимости с Happ и V2RayTun
            logger.info(f"subscription-userinfo (строковый формат для Happ и V2RayTun): {subscription_userinfo_happ}")
            
            # Логируем информацию о подписке для отладки
            import datetime
            expire_datetime = datetime.datetime.fromtimestamp(sub["expires_at"])
            expire_str = expire_datetime.strftime('%Y-%m-%d %H:%M:%S')
            logger.info(f"Устанавливаем название группы подписки (Remarks для V2RayTun): '{vpn_brand_name}'")
            logger.info(f"Время истечения подписки: {expire_str} (timestamp: {sub['expires_at']})")
            logger.info(f"Домен для Happ клиента: '{domain_name}' (из '{vpn_brand_name}')")
            if website_url:
                logger.info(f"Ссылка на сайт: {website_url}")
            if telegram_url:
                logger.info(f"Ссылка на Telegram: {telegram_url}")
            
            # Возвращаем как text/plain (стандартный Content-Type для subscription)
            # Добавляем CORS заголовки и Subscription-UserInfo для VPN клиентов
            # Для Happ пробуем разные варианты заголовков для автоматического определения названия
            # ВАЖНО: HTTP заголовки должны быть в ASCII/latin-1, без эмодзи!
            import urllib.parse
            # Убираем эмодзи из имени файла для Content-Disposition
            clean_filename = re.sub(r'[^\w\s-]', '', vpn_brand_name).strip().replace(' ', '-').lower()
            if not clean_filename:
                clean_filename = 'daralla-vpn'
            
            # clean_name_for_header уже определен выше при формировании комментариев
            
            headers = {
                "Content-Type": "text/plain; charset=utf-8",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "*",
                # Используем один заголовок subscription-userinfo в строковом формате для совместимости с Happ и V2RayTun
                # V2RayTun поддерживает строковый формат: "upload=0; download=100000; total=2000000; expire=1749954800"
                "subscription-userinfo": subscription_userinfo_happ,  # Строковый формат для Happ и V2RayTun (upload=0; download=0; total=0; expire=...)
                "Content-Disposition": f'attachment; filename="{clean_filename}"',  # Имя файла для Happ (attachment вместо inline)
                "new-domain": domain_name,  # Заголовок для Happ VPN клиента (определяет название группы вместо домена из URL)
                "X-Subscription-Name": clean_name_for_header,  # Дополнительный заголовок с названием (БЕЗ эмодзи, только ASCII)
                "profile-title": clean_name_for_header,  # Название профиля для Happ и V2RayTun (максимум 25 символов для Happ)
                "profile-update-interval": "1",  # Интервал обновления подписки в часах для Happ и V2RayTun
            }
            
            # Добавляем дополнительные заголовки, которые могут поддерживаться некоторыми клиентами
            # (на основе информации из Marzban и других источников, но без официальной документации)
            # Эти заголовки могут использоваться для отображения кнопок и названия в клиентах
            
            # V2RayTun и Happ получают всю информацию из subscription-userinfo заголовка
            # Дополнительные заголовки могут вызывать конфликты, поэтому используем только основные
            
            # Заголовки для ссылок согласно официальной документации Happ VPN и V2RayTun
            # Happ использует profile-web-page-url для сайта (левая иконка) и support-url для поддержки (правая иконка)
            # V2RayTun может не поддерживать кнопки через заголовки напрямую, но поддерживает announce с announce-url
            if website_url:
                headers["profile-web-page-url"] = website_url  # Кнопка сайта для Happ (левая иконка)
                # Также добавляем для совместимости с другими клиентами
                headers["website"] = website_url
                
            if telegram_url:
                # support-url используется для кнопки поддержки/Telegram (правая иконка в Happ)
                # Если ссылка ведет в Telegram, Happ автоматически покажет иконку Telegram
                headers["support-url"] = telegram_url  # Кнопка поддержки для Happ
                # Также добавляем для совместимости с другими клиентами
                headers["telegram-url"] = telegram_url
                headers["telegram"] = telegram_url
                headers["tg"] = telegram_url
                
                # Добавляем announce в HTTP заголовках для V2RayTun (НЕ в комментариях, чтобы Happ не показывал)
                # V2RayTun поддерживает announce в заголовках, Happ обычно игнорирует announce в заголовках
                # Это обеспечивает единообразное оформление: Happ использует кнопки, V2RayTun использует announce
                if not is_happ_client:
                    # Формируем announce текст только с Telegram (без сайта) для V2RayTun
                    announce_text = "#0088cc📱 Telegram"  # Цветной текст: #0088cc (синий Telegram)
                    # Кодируем в base64 для V2RayTun (V2RayTun поддерживает base64 с префиксом base64:)
                    import base64
                    announce_base64 = base64.b64encode(announce_text.encode('utf-8')).decode('utf-8')
                    headers["announce"] = f"base64:{announce_base64}"
                    headers["announce-url"] = telegram_url
                    logger.debug(f"Добавлен announce в заголовках для V2RayTun (клиент: {user_agent[:50] if user_agent else 'unknown'})")
                else:
                    logger.debug(f"Пропущен announce в заголовках для Happ клиента (используются кнопки через заголовки)")
            
            
            return (response_text, 200, headers)
            
        except Exception as e:
            logger.error(f"Ошибка в эндпоинте /sub/<token>: {e}")
            return ("Internal server error", 500)
    
    # API endpoint для получения подписок пользователя (для Telegram Mini App)
    @app.route('/api/subscriptions', methods=['GET', 'OPTIONS'])
    def api_subscriptions():
        """API endpoint для получения подписок пользователя через Telegram Mini App"""
        # Обрабатываем OPTIONS запрос (CORS preflight)
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
        
        try:
            # Получаем initData из query параметров
            init_data = request.args.get('initData')
            if not init_data:
                return jsonify({'error': 'initData is required'}), 400
            
            # Проверяем initData от Telegram
            user_id = verify_telegram_init_data(init_data)
            if not user_id:
                logger.warning("Invalid initData from Telegram Mini App")
                return jsonify({'error': 'Invalid authentication'}), 401
            
            # Получаем подписки пользователя
            from ...db.subscribers_db import get_all_subscriptions_by_user
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                subscriptions = loop.run_until_complete(get_all_subscriptions_by_user(user_id))
            finally:
                loop.close()
            
            # Форматируем данные для ответа
            import time
            import datetime
            current_time = int(time.time())
            
            formatted_subs = []
            for sub in subscriptions:
                expires_at = sub['expires_at']
                is_active = sub['status'] == 'active' and expires_at > current_time
                is_expired = expires_at < current_time
                
                expiry_datetime = datetime.datetime.fromtimestamp(expires_at)
                created_datetime = datetime.datetime.fromtimestamp(sub['created_at'])
                
                formatted_subs.append({
                    'id': sub['id'],
                    'name': sub.get('name', f"Подписка {sub['id']}"),
                    'status': 'active' if is_active else ('expired' if is_expired else sub['status']),
                    'period': sub['period'],
                    'device_limit': sub['device_limit'],
                    'created_at': sub['created_at'],
                    'created_at_formatted': created_datetime.strftime('%d.%m.%Y %H:%M'),
                    'expires_at': expires_at,
                    'expires_at_formatted': expiry_datetime.strftime('%d.%m.%Y %H:%M'),
                    'price': sub['price'],
                    'token': sub['subscription_token'],
                    'days_remaining': max(0, (expires_at - current_time) // (24 * 60 * 60)) if is_active else 0
                })
            
            # Сортируем: сначала активные, потом по дате создания
            formatted_subs.sort(key=lambda x: (x['status'] != 'active', -x['created_at']))
            
            return jsonify({
                'success': True,
                'subscriptions': formatted_subs,
                'total': len(formatted_subs),
                'active': len([s for s in formatted_subs if s['status'] == 'active'])
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
            
        except Exception as e:
            logger.error(f"Ошибка в API /api/subscriptions: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
    
    @app.route('/api/user/payment/create', methods=['POST', 'OPTIONS'])
    def api_user_payment_create():
        """API endpoint для создания платежа (покупка или продление подписки)"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
        
        try:
            data = request.get_json() or {}
            init_data = data.get('initData') or request.args.get('initData')
            
            if not init_data:
                return jsonify({'error': 'initData is required'}), 400
            
            # Проверяем initData от Telegram
            user_id = verify_telegram_init_data(init_data)
            if not user_id:
                logger.warning("Invalid initData from Telegram Mini App")
                return jsonify({'error': 'Invalid authentication'}), 401
            
            # Получаем параметры платежа
            period = data.get('period')  # 'month' или '3month'
            subscription_id = data.get('subscription_id')  # Для продления
            
            if not period or period not in ['month', '3month']:
                return jsonify({'error': 'Invalid period. Use "month" or "3month"'}), 400
            
            # Определяем цену
            price = "150.00" if period == "month" else "350.00"
            
            # Импортируем необходимые модули
            from yookassa import Payment
            from ...db import add_payment, get_pending_payment, PAYMENTS_DB_PATH
            import uuid
            import datetime
            import json
            import aiosqlite
            
            # Проверяем существующие pending платежи и отменяем их
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Отменяем старые pending платежи
                async def cancel_old_payments():
                    async with aiosqlite.connect(PAYMENTS_DB_PATH) as db:
                        await db.execute(
                            'UPDATE payments SET status = ? WHERE user_id = ? AND status = ?',
                            ('canceled', user_id, 'pending')
                        )
                        await db.commit()
                
                loop.run_until_complete(cancel_old_payments())
                
                # Создаем уникальный email для подписки
                now = int(datetime.datetime.now().timestamp())
                subscription_uuid = str(uuid.uuid4())
                unique_email = f'{user_id}_{subscription_uuid}'
                
                # Формируем period для платежа
                payment_period = f"extend_sub_{period}" if subscription_id else period
                
                # Создаем платеж через YooKassa
                payment = Payment.create({
                    "amount": {"value": price, "currency": "RUB"},
                    "confirmation": {"type": "redirect", "return_url": f"https://t.me/{user_id}"},
                    "capture": True,
                    "description": f"VPN {period} для {user_id}",
                    "metadata": {
                        "user_id": user_id,
                        "type": payment_period,
                        "device_limit": 1,
                        "unique_email": unique_email,
                        "price": price,
                    },
                    "receipt": {
                        "customer": {"email": f"{user_id}@vpn-x3.ru"},
                        "items": [{
                            "description": f"VPN {period} для {user_id}",
                            "quantity": "1.00",
                            "amount": {"value": price, "currency": "RUB"},
                            "vat_code": 1
                        }]
                    }
                })
                
                # Добавляем subscription_id в метаданные для продления
                payment_meta = {
                    "price": price,
                    "type": payment_period,
                    "unique_email": unique_email,
                    "message_id": None
                }
                
                if subscription_id:
                    payment_meta['extension_subscription_id'] = int(subscription_id)
                
                # Сохраняем платеж в БД
                async def save_payment():
                    await add_payment(
                        payment_id=payment.id,
                        user_id=user_id,
                        status='pending',
                        meta=payment_meta
                    )
                
                loop.run_until_complete(save_payment())
                
            finally:
                loop.close()
            
            return jsonify({
                'success': True,
                'payment_id': payment.id,
                'payment_url': payment.confirmation.confirmation_url,
                'amount': price,
                'period': period
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
            
        except Exception as e:
            logger.error(f"Ошибка в API /api/user/payment/create: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
    
    @app.route('/api/user/payment/status/<payment_id>', methods=['GET', 'OPTIONS'])
    def api_user_payment_status(payment_id):
        """API endpoint для проверки статуса платежа"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
        
        try:
            init_data = request.args.get('initData')
            
            if not init_data:
                return jsonify({'error': 'initData is required'}), 400
            
            # Проверяем initData от Telegram
            user_id = verify_telegram_init_data(init_data)
            if not user_id:
                logger.warning("Invalid initData from Telegram Mini App")
                return jsonify({'error': 'Invalid authentication'}), 401
            
            # Получаем информацию о платеже
            from ...db import get_payment_by_id
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                payment_info = loop.run_until_complete(get_payment_by_id(payment_id))
            finally:
                loop.close()
            
            if not payment_info:
                return jsonify({'error': 'Payment not found'}), 404
            
            # Проверяем, что платеж принадлежит пользователю
            if payment_info['user_id'] != user_id:
                return jsonify({'error': 'Access denied'}), 403
            
            return jsonify({
                'success': True,
                'payment_id': payment_id,
                'status': payment_info['status'],
                'activated': bool(payment_info.get('activated', 0))
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
            
        except Exception as e:
            logger.error(f"Ошибка в API /api/user/payment/status/{payment_id}: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
    
    @app.route('/api/user/subscription/<int:sub_id>/rename', methods=['POST', 'OPTIONS'])
    def api_user_subscription_rename(sub_id):
        """API endpoint для переименования подписки пользователя"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
        
        try:
            data = request.get_json() or {}
            init_data = data.get('initData') or request.args.get('initData')
            
            if not init_data:
                return jsonify({'error': 'initData is required'}), 400
            
            # Проверяем initData от Telegram
            user_id = verify_telegram_init_data(init_data)
            if not user_id:
                logger.warning("Invalid initData from Telegram Mini App")
                return jsonify({'error': 'Invalid authentication'}), 401
            
            # Получаем новое имя
            new_name = data.get('name', '').strip()
            if not new_name:
                return jsonify({'error': 'Name is required'}), 400
            
            # Проверяем, что подписка принадлежит пользователю
            from ...db.subscribers_db import get_subscription_by_id, update_subscription_name
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                sub = loop.run_until_complete(get_subscription_by_id(sub_id, user_id))
                if not sub:
                    return jsonify({'error': 'Subscription not found or access denied'}), 404
                
                # Обновляем имя подписки
                loop.run_until_complete(update_subscription_name(sub_id, new_name))
            finally:
                loop.close()
            
            return jsonify({
                'success': True,
                'message': 'Subscription renamed successfully',
                'name': new_name
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
            
        except Exception as e:
            logger.error(f"Ошибка в API /api/user/subscription/{sub_id}/rename: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
    
    @app.route('/api/user/server-usage', methods=['GET', 'OPTIONS'])
    def api_user_server_usage():
        """API endpoint для получения данных о серверах и их использовании пользователем"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
        
        try:
            init_data = request.args.get('initData')
            if not init_data:
                return jsonify({'error': 'initData is required'}), 400
            
            user_id = verify_telegram_init_data(init_data)
            if not user_id:
                return jsonify({'error': 'Invalid authentication'}), 401
            
            from ...db.subscribers_db import get_user_server_usage
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                server_usage = loop.run_until_complete(get_user_server_usage(user_id))
            finally:
                loop.close()
            
            # Получаем информацию о серверах (координаты, display_name) из конфигурации
            def get_servers_info():
                try:
                    from ... import bot as bot_module
                    server_manager = getattr(bot_module, 'server_manager', None)
                    if not server_manager:
                        return []
                    
                    servers_info = []
                    for location, servers in server_manager.servers_by_location.items():
                        for server in servers:
                            server_name = server['name']
                            display_name = server['config'].get('display_name', server_name)
                            lat = server['config'].get('lat')
                            lng = server['config'].get('lng')
                            
                            if lat is not None and lng is not None:
                                usage_data = server_usage.get(server_name, {'count': 0, 'percentage': 0})
                                servers_info.append({
                                    'name': server_name,
                                    'display_name': display_name,
                                    'location': location,
                                    'lat': lat,
                                    'lng': lng,
                                    'usage_count': usage_data['count'],
                                    'usage_percentage': usage_data['percentage']
                                })
                    return servers_info
                except (ImportError, AttributeError) as e:
                    logger.error(f"Ошибка получения информации о серверах: {e}")
                    return []
            
            servers_info = get_servers_info()
            
            return jsonify({
                'success': True,
                'servers': servers_info
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в API /api/user/server-usage: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500
    
    # API endpoint для получения статуса серверов (для Telegram Mini App)
    @app.route('/api/servers', methods=['GET', 'OPTIONS'])
    def api_servers():
        """API endpoint для получения статуса серверов через Telegram Mini App"""
        # Обрабатываем OPTIONS запрос (CORS preflight)
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
        
        try:
            # Получаем initData из query параметров
            init_data = request.args.get('initData')
            if not init_data:
                return jsonify({'error': 'initData is required'}), 400
            
            # Проверяем initData от Telegram
            user_id = verify_telegram_init_data(init_data)
            if not user_id:
                return jsonify({'error': 'Invalid initData'}), 401
            
            # Получаем server_manager из bot_app
            def get_server_manager():
                """Получает server_manager из bot.py"""
                try:
                    from ... import bot as bot_module
                    return getattr(bot_module, 'server_manager', None)
                except (ImportError, AttributeError):
                    return None
            
            server_manager = get_server_manager()
            if not server_manager:
                return jsonify({'error': 'Server manager not available'}), 503
            
            # Получаем статус серверов
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Проверяем здоровье всех серверов
                health_results = server_manager.check_all_servers_health(force_check=False)
                health_status = server_manager.get_server_health_status()
                
                # Формируем список серверов
                servers = []
                for server in server_manager.servers:
                    server_name = server["name"]
                    is_healthy = health_results.get(server_name, False)
                    status_info = health_status.get(server_name, {})
                    
                    # Форматируем дату последней проверки
                    last_check = None
                    if status_info.get('last_check'):
                        import datetime
                        if isinstance(status_info['last_check'], (int, float)):
                            last_check = datetime.datetime.fromtimestamp(status_info['last_check']).strftime('%d.%m.%Y %H:%M')
                        else:
                            last_check = str(status_info['last_check'])
                    
                    servers.append({
                        'name': server_name,
                        'status': 'online' if is_healthy else 'offline',
                        'last_check': last_check
                    })
                
                return jsonify({
                    'success': True,
                    'servers': servers
                }), 200, {
                    "Access-Control-Allow-Origin": "*",
                    "Content-Type": "application/json"
                }
            finally:
                loop.close()
            
        except Exception as e:
            logger.error(f"Ошибка в API /api/servers: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
    
    # Endpoint для обслуживания веб-приложения
    @app.route('/webapp/', methods=['GET'])
    @app.route('/webapp/index.html', methods=['GET'])
    def webapp_index():
        """Отдает HTML страницу веб-приложения"""
        try:
            import os
            # Путь: bot/handlers/webhooks/webhook_app.py -> поднимаемся на 4 уровня до /app/, затем webapp/
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            webapp_path = os.path.join(base_dir, 'webapp', 'index.html')
            if os.path.exists(webapp_path):
                with open(webapp_path, 'r', encoding='utf-8') as f:
                    return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}
            else:
                logger.warning(f"Web app not found at: {webapp_path}")
                return "Web app not found", 404
        except Exception as e:
            logger.error(f"Ошибка при загрузке webapp: {e}", exc_info=True)
            return "Error loading web app", 500
    
    # Endpoint для статических файлов (CSS, JS)
    @app.route('/webapp/<path:filename>', methods=['GET'])
    def webapp_static(filename):
        """Отдает статические файлы веб-приложения"""
        try:
            import os
            # Путь: bot/handlers/webhooks/webhook_app.py -> поднимаемся на 4 уровня до /app/, затем webapp/
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            webapp_dir = os.path.join(base_dir, 'webapp')
            file_path = os.path.join(webapp_dir, filename)
            
            # Проверка безопасности (только файлы из webapp директории)
            webapp_dir_abs = os.path.abspath(webapp_dir)
            file_path_abs = os.path.abspath(file_path)
            if not file_path_abs.startswith(webapp_dir_abs):
                logger.warning(f"Forbidden file access attempt: {file_path}")
                return "Forbidden", 403
            
            if os.path.exists(file_path) and os.path.isfile(file_path):
                # Определяем Content-Type по расширению
                content_type = 'text/plain'
                if filename.endswith('.css'):
                    content_type = 'text/css'
                elif filename.endswith('.js'):
                    content_type = 'application/javascript'
                elif filename.endswith('.json'):
                    content_type = 'application/json'
                
                with open(file_path, 'rb') as f:
                    return f.read(), 200, {'Content-Type': content_type}
            else:
                return "File not found", 404
        except Exception as e:
            logger.error(f"Ошибка при загрузке статического файла: {e}")
            return "Error loading file", 500
    
    # ==================== АДМИН API ====================
    
    def check_admin_access(user_id: str) -> bool:
        """Проверяет, является ли пользователь админом"""
        try:
            from ... import bot as bot_module
            ADMIN_IDS = getattr(bot_module, 'ADMIN_IDS', [])
            
            # Логируем для отладки
            logger.info(f"Проверка прав админа для user_id={user_id}, ADMIN_IDS={ADMIN_IDS}")
            
            # Преобразуем user_id в строку для сравнения
            user_id_str = str(user_id)
            
            # Проверяем, является ли user_id админом
            # ADMIN_IDS может быть списком строк или чисел
            for admin_id in ADMIN_IDS:
                if str(admin_id) == user_id_str:
                    logger.info(f"Пользователь {user_id} является админом")
                    return True
            
            logger.info(f"Пользователь {user_id} НЕ является админом")
            return False
        except Exception as e:
            logger.error(f"Ошибка при проверке прав админа: {e}", exc_info=True)
            return False
    
    @app.route('/api/admin/check', methods=['POST', 'OPTIONS'])
    def api_admin_check():
        """Проверка прав админа"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
        
        try:
            data = request.get_json() or {}
            init_data = data.get('initData') or request.args.get('initData')
            
            if not init_data:
                return jsonify({'error': 'initData is required'}), 400
            
            user_id = verify_telegram_init_data(init_data)
            if not user_id:
                return jsonify({'error': 'Invalid authentication'}), 401
            
            is_admin = check_admin_access(user_id)
            
            return jsonify({
                'success': True,
                'is_admin': is_admin
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/check: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500
    
    @app.route('/api/admin/users', methods=['POST', 'OPTIONS'])
    def api_admin_users():
        """Список пользователей с поиском и пагинацией"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
        
        try:
            data = request.get_json() or {}
            init_data = data.get('initData') or request.args.get('initData')
            search = data.get('search', '').strip()
            page = int(data.get('page', 1))
            limit = int(data.get('limit', 20))
            
            if not init_data:
                return jsonify({'error': 'initData is required'}), 400
            
            user_id = verify_telegram_init_data(init_data)
            if not user_id:
                return jsonify({'error': 'Invalid authentication'}), 401
            
            if not check_admin_access(user_id):
                return jsonify({'error': 'Access denied'}), 403
            
            from ...db.subscribers_db import DB_PATH
            import aiosqlite
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                async def get_users():
                    async with aiosqlite.connect(DB_PATH) as db:
                        db.row_factory = aiosqlite.Row
                        
                        # Базовый запрос
                        query = "SELECT * FROM users WHERE 1=1"
                        params = []
                        
                        # Поиск по user_id
                        if search:
                            query += " AND user_id LIKE ?"
                            params.append(f"%{search}%")
                        
                        # Подсчет общего количества
                        count_query = f"SELECT COUNT(*) as count FROM ({query})"
                        async with db.execute(count_query, params) as cur:
                            row = await cur.fetchone()
                            total = row['count'] if row else 0
                        
                        # Получение данных с пагинацией
                        query += " ORDER BY last_seen DESC LIMIT ? OFFSET ?"
                        params.extend([limit, (page - 1) * limit])
                        
                        async with db.execute(query, params) as cur:
                            rows = await cur.fetchall()
                            users = []
                            for row in rows:
                                # Получаем количество подписок для каждого пользователя
                                async with db.execute(
                                    "SELECT COUNT(*) as count FROM subscriptions s JOIN users u ON s.subscriber_id = u.id WHERE u.user_id = ?",
                                    (row['user_id'],)
                                ) as sub_cur:
                                    sub_row = await sub_cur.fetchone()
                                    sub_count = sub_row['count'] if sub_row else 0
                                
                                users.append({
                                    'id': row['id'],
                                    'user_id': row['user_id'],
                                    'first_seen': row['first_seen'],
                                    'last_seen': row['last_seen'],
                                    'subscriptions_count': sub_count
                                })
                            
                            return users, total
                
                users, total = loop.run_until_complete(get_users())
            finally:
                loop.close()
            
            return jsonify({
                'success': True,
                'users': users,
                'total': total,
                'page': page,
                'limit': limit,
                'pages': (total + limit - 1) // limit if limit > 0 else 0
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/users: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500
    
    @app.route('/api/admin/user/<user_id_param>', methods=['POST', 'OPTIONS'])
    def api_admin_user_info(user_id_param):
        """Информация о пользователе"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
        
        try:
            data = request.get_json() or {}
            init_data = data.get('initData') or request.args.get('initData')
            
            if not init_data:
                return jsonify({'error': 'initData is required'}), 400
            
            admin_id = verify_telegram_init_data(init_data)
            if not admin_id:
                return jsonify({'error': 'Invalid authentication'}), 401
            
            if not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
            
            from ...db.subscribers_db import get_user_by_id, get_all_subscriptions_by_user
            from ...db.payments_db import get_payments_by_user
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                user = loop.run_until_complete(get_user_by_id(user_id_param))
                if not user:
                    return jsonify({'error': 'User not found'}), 404
                
                subscriptions = loop.run_until_complete(get_all_subscriptions_by_user(user_id_param))
                payments = loop.run_until_complete(get_payments_by_user(user_id_param, limit=10))
            finally:
                loop.close()
            
            import datetime
            import time
            current_time = int(time.time())
            
            # Форматируем подписки
            formatted_subs = []
            for sub in subscriptions:
                expires_at = sub['expires_at']
                is_active = sub['status'] == 'active' and expires_at > current_time
                
                formatted_subs.append({
                    'id': sub['id'],
                    'name': sub.get('name', f"Подписка {sub['id']}"),
                    'status': sub['status'],
                    'is_active': is_active,
                    'period': sub['period'],
                    'device_limit': sub['device_limit'],
                    'created_at': sub['created_at'],
                    'created_at_formatted': datetime.datetime.fromtimestamp(sub['created_at']).strftime('%d.%m.%Y %H:%M'),
                    'expires_at': expires_at,
                    'expires_at_formatted': datetime.datetime.fromtimestamp(expires_at).strftime('%d.%m.%Y %H:%M'),
                    'price': sub['price'],
                    'token': sub['subscription_token']
                })
            
            # Форматируем платежи
            formatted_payments = []
            for payment in payments:
                # Безопасно получаем данные из payment
                payment_id = payment.get('payment_id') or payment.get('id', 'N/A')
                status = payment.get('status', 'unknown')
                created_at = payment.get('created_at', 0)
                
                # amount может быть в meta (как price или amount) или отсутствовать
                amount = 0
                meta = payment.get('meta', {})
                if isinstance(meta, dict):
                    amount = meta.get('price') or meta.get('amount', 0)
                elif isinstance(meta, str):
                    try:
                        import json
                        meta_dict = json.loads(meta)
                        amount = meta_dict.get('price') or meta_dict.get('amount', 0)
                    except:
                        amount = 0
                
                # Преобразуем строку в число, если нужно
                if isinstance(amount, str):
                    try:
                        amount = float(amount)
                    except (ValueError, TypeError):
                        amount = 0
                
                formatted_payments.append({
                    'id': payment_id,
                    'amount': amount,
                    'status': status,
                    'created_at': created_at,
                    'created_at_formatted': datetime.datetime.fromtimestamp(created_at).strftime('%d.%m.%Y %H:%M') if created_at else 'N/A'
                })
            
            return jsonify({
                'success': True,
                'user': {
                    'user_id': user['user_id'],
                    'first_seen': user['first_seen'],
                    'first_seen_formatted': datetime.datetime.fromtimestamp(user['first_seen']).strftime('%d.%m.%Y %H:%M'),
                    'last_seen': user['last_seen'],
                    'last_seen_formatted': datetime.datetime.fromtimestamp(user['last_seen']).strftime('%d.%m.%Y %H:%M')
                },
                'subscriptions': formatted_subs,
                'payments': formatted_payments
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/user: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500
    
    @app.route('/api/admin/subscription/<int:sub_id>', methods=['POST', 'OPTIONS'])
    def api_admin_subscription_info(sub_id):
        """Информация о подписке"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
        
        try:
            data = request.get_json() or {}
            init_data = data.get('initData') or request.args.get('initData')
            
            if not init_data:
                return jsonify({'error': 'initData is required'}), 400
            
            admin_id = verify_telegram_init_data(init_data)
            if not admin_id:
                return jsonify({'error': 'Invalid authentication'}), 401
            
            if not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
            
            from ...db.subscribers_db import get_subscription_by_id_only, get_subscription_servers
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                sub = loop.run_until_complete(get_subscription_by_id_only(sub_id))
                if not sub:
                    return jsonify({'error': 'Subscription not found'}), 404
                
                servers = loop.run_until_complete(get_subscription_servers(sub_id))
            finally:
                loop.close()
            
            import datetime
            
            return jsonify({
                'success': True,
                'subscription': {
                    'id': sub['id'],
                    'name': sub.get('name', f"Подписка {sub['id']}"),
                    'status': sub['status'],
                    'period': sub['period'],
                    'device_limit': sub['device_limit'],
                    'created_at': sub['created_at'],
                    'created_at_formatted': datetime.datetime.fromtimestamp(sub['created_at']).strftime('%d.%m.%Y %H:%M'),
                    'expires_at': sub['expires_at'],
                    'expires_at_formatted': datetime.datetime.fromtimestamp(sub['expires_at']).strftime('%d.%m.%Y %H:%M'),
                    'price': sub['price'],
                    'token': sub['subscription_token']
                },
                'servers': servers
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/subscription: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500
    
    @app.route('/api/admin/subscription/<int:sub_id>/update', methods=['POST', 'OPTIONS'])
    def api_admin_subscription_update(sub_id):
        """Обновление подписки"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
        
        try:
            data = request.get_json() or {}
            init_data = data.get('initData') or request.args.get('initData')
            
            if not init_data:
                return jsonify({'error': 'initData is required'}), 400
            
            admin_id = verify_telegram_init_data(init_data)
            if not admin_id:
                return jsonify({'error': 'Invalid authentication'}), 401
            
            if not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
            
            # Получаем данные для обновления
            updates = {}
            if 'name' in data:
                updates['name'] = data['name']
            if 'expires_at' in data:
                updates['expires_at'] = int(data['expires_at'])
            if 'device_limit' in data:
                updates['device_limit'] = int(data['device_limit'])
            if 'status' in data:
                updates['status'] = data['status']
            
            if not updates:
                return jsonify({'error': 'No fields to update'}), 400
            
            from ...db.subscribers_db import get_subscription_by_id_only, update_subscription_name, update_subscription_expiry, update_subscription_status, DB_PATH
            import aiosqlite
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Проверяем существование подписки
                sub = loop.run_until_complete(get_subscription_by_id_only(sub_id))
                if not sub:
                    return jsonify({'error': 'Subscription not found'}), 404
                
                # Обновляем поля
                if 'name' in updates:
                    loop.run_until_complete(update_subscription_name(sub_id, updates['name']))
                
                if 'expires_at' in updates:
                    loop.run_until_complete(update_subscription_expiry(sub_id, updates['expires_at']))
                
                if 'device_limit' in updates:
                    async def update_device_limit():
                        async with aiosqlite.connect(DB_PATH) as db:
                            await db.execute(
                                "UPDATE subscriptions SET device_limit = ? WHERE id = ?",
                                (updates['device_limit'], sub_id)
                            )
                            await db.commit()
                    loop.run_until_complete(update_device_limit())
                
                if 'status' in updates:
                    loop.run_until_complete(update_subscription_status(sub_id, updates['status']))
                
                # Получаем обновленную подписку
                updated_sub = loop.run_until_complete(get_subscription_by_id_only(sub_id))
            finally:
                loop.close()
            
            import datetime
            
            return jsonify({
                'success': True,
                'subscription': {
                    'id': updated_sub['id'],
                    'name': updated_sub.get('name', f"Подписка {updated_sub['id']}"),
                    'status': updated_sub['status'],
                    'period': updated_sub['period'],
                    'device_limit': updated_sub['device_limit'],
                    'created_at': updated_sub['created_at'],
                    'created_at_formatted': datetime.datetime.fromtimestamp(updated_sub['created_at']).strftime('%d.%m.%Y %H:%M'),
                    'expires_at': updated_sub['expires_at'],
                    'expires_at_formatted': datetime.datetime.fromtimestamp(updated_sub['expires_at']).strftime('%d.%m.%Y %H:%M'),
                    'price': updated_sub['price'],
                    'token': updated_sub['subscription_token']
                }
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/subscription/update: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500
    
    @app.route('/api/admin/subscription/<int:sub_id>/sync', methods=['POST', 'OPTIONS'])
    def api_admin_subscription_sync(sub_id):
        """Синхронизация подписки с X-UI серверами"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
        
        try:
            data = request.get_json() or {}
            init_data = data.get('initData') or request.args.get('initData')
            
            if not init_data:
                return jsonify({'error': 'initData is required'}), 400
            
            admin_id = verify_telegram_init_data(init_data)
            if not admin_id:
                return jsonify({'error': 'Invalid authentication'}), 401
            
            if not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
            
            from ...db.subscribers_db import get_subscription_by_id_only, get_subscription_servers
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                sub = loop.run_until_complete(get_subscription_by_id_only(sub_id))
                if not sub:
                    return jsonify({'error': 'Subscription not found'}), 404
                
                servers = loop.run_until_complete(get_subscription_servers(sub_id))
                
                # Получаем subscription_manager
                def get_subscription_manager():
                    try:
                        from ... import bot as bot_module
                        return getattr(bot_module, 'subscription_manager', None)
                    except (ImportError, AttributeError):
                        return None
                
                subscription_manager = get_subscription_manager()
                if not subscription_manager:
                    return jsonify({'error': 'Subscription manager not available'}), 503
                
                # Получаем user_id из подписки
                async def get_user_id_from_sub():
                    import aiosqlite
                    from ...db.subscribers_db import DB_PATH
                    async with aiosqlite.connect(DB_PATH) as db:
                        db.row_factory = aiosqlite.Row
                        async with db.execute(
                            "SELECT u.user_id FROM users u JOIN subscriptions s ON u.id = s.subscriber_id WHERE s.id = ?",
                            (sub_id,)
                        ) as cur:
                            row = await cur.fetchone()
                            return row['user_id'] if row else ''
                
                user_id = loop.run_until_complete(get_user_id_from_sub())
                
                # Синхронизируем с каждым сервером
                async def sync_all_servers():
                    sync_results = []
                    for server_info in servers:
                        server_name = server_info['server_name']
                        client_email = server_info['client_email']
                        
                        try:
                            # Синхронизируем основные данные (expires_at, device_limit)
                            await subscription_manager.ensure_client_on_server(
                                subscription_id=sub_id,
                                server_name=server_name,
                                client_email=client_email,
                                user_id=user_id,
                                expires_at=sub['expires_at'],
                                token=sub['subscription_token'],
                                device_limit=sub['device_limit']
                            )
                            
                            # Синхронизируем имя подписки (name -> subId на сервере)
                            # Получаем имя подписки из БД
                            subscription_name = sub.get('name', sub['subscription_token'])
                            
                            # Получаем X-UI сервер для обновления имени
                            xui, resolved_name = subscription_manager.server_manager.get_server_by_name(server_name)
                            if xui:
                                try:
                                    # Проверяем текущее имя на сервере
                                    client_info = xui.get_client_info(client_email)
                                    if client_info:
                                        current_sub_id = client_info['client'].get('subId', '')
                                        # Если имя отличается, синхронизируем
                                        if current_sub_id != subscription_name:
                                            logger.info(
                                                f"Синхронизация имени подписки на сервере {server_name}: "
                                                f"'{current_sub_id}' -> '{subscription_name}'"
                                            )
                                            xui.updateClientName(client_email, subscription_name)
                                            logger.info(f"Имя подписки синхронизировано на сервере {server_name}")
                                        else:
                                            logger.debug(f"Имя подписки на сервере {server_name} уже совпадает: '{subscription_name}'")
                                except Exception as name_sync_e:
                                    logger.warning(f"Ошибка синхронизации имени подписки на сервере {server_name}: {name_sync_e}")
                            
                            sync_results.append({
                                'server': server_name,
                                'status': 'success'
                            })
                        except Exception as e:
                            logger.error(f"Ошибка синхронизации с сервером {server_name}: {e}")
                            sync_results.append({
                                'server': server_name,
                                'status': 'error',
                                'error': str(e)
                            })
                    return sync_results
                
                sync_results = loop.run_until_complete(sync_all_servers())
            finally:
                loop.close()
            
            return jsonify({
                'success': True,
                'sync_results': sync_results
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/subscription/sync: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500
    
    @app.route('/api/admin/subscription/<int:sub_id>/delete', methods=['POST', 'OPTIONS'])
    def api_admin_subscription_delete(sub_id):
        """Удаление подписки"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
        
        try:
            data = request.get_json() or {}
            init_data = data.get('initData') or request.args.get('initData')
            confirm = data.get('confirm', False)  # Требуем подтверждение
            
            if not init_data:
                return jsonify({'error': 'initData is required'}), 400
            
            if not confirm:
                return jsonify({'error': 'Confirmation required'}), 400
            
            admin_id = verify_telegram_init_data(init_data)
            if not admin_id:
                return jsonify({'error': 'Invalid authentication'}), 401
            
            if not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
            
            from ...db.subscribers_db import get_subscription_by_id_only, get_subscription_servers, remove_subscription_server, DB_PATH
            import aiosqlite
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Проверяем существование подписки
                sub = loop.run_until_complete(get_subscription_by_id_only(sub_id))
                if not sub:
                    return jsonify({'error': 'Subscription not found'}), 404
                
                # Получаем все серверы подписки
                servers = loop.run_until_complete(get_subscription_servers(sub_id))
                
                # Получаем менеджеры
                def get_managers():
                    try:
                        from ... import bot as bot_module
                        return {
                            'subscription_manager': getattr(bot_module, 'subscription_manager', None),
                            'server_manager': getattr(bot_module, 'server_manager', None)
                        }
                    except (ImportError, AttributeError):
                        return {'subscription_manager': None, 'server_manager': None}
                
                managers = get_managers()
                server_manager = managers.get('server_manager')
                
                # 1. Удаляем клиентов со всех серверов
                async def delete_clients_from_servers():
                    deleted = []
                    failed = []
                    if server_manager and servers:
                        for server_info in servers:
                            server_name = server_info['server_name']
                            client_email = server_info['client_email']
                            
                            try:
                                xui, _ = server_manager.get_server_by_name(server_name)
                                if xui:
                                    xui.deleteClient(client_email)
                                    deleted.append(server_name)
                                    logger.info(
                                        f"Удален клиент {client_email} с сервера {server_name} "
                                        f"при удалении подписки {sub_id}"
                                    )
                                else:
                                    failed.append(server_name)
                                    logger.warning(f"Сервер {server_name} не найден в server_manager")
                            except Exception as e:
                                failed.append(server_name)
                                logger.error(
                                    f"Ошибка удаления клиента {client_email} с сервера {server_name}: {e}"
                                )
                    return deleted, failed
                
                deleted_servers, failed_servers = loop.run_until_complete(delete_clients_from_servers())
                
                # 2. Удаляем связи подписки с серверами из БД
                for server_info in servers:
                    try:
                        loop.run_until_complete(remove_subscription_server(sub_id, server_info['server_name']))
                    except Exception as e:
                        logger.error(f"Ошибка удаления связи подписки {sub_id} с сервером {server_info['server_name']}: {e}")
                
                # 3. Удаляем подписку из БД
                async def delete_subscription():
                    async with aiosqlite.connect(DB_PATH) as db:
                        await db.execute("DELETE FROM subscriptions WHERE id = ?", (sub_id,))
                        await db.commit()
                
                loop.run_until_complete(delete_subscription())
                
                logger.info(f"Админ {admin_id} удалил подписку {sub_id}")
            finally:
                loop.close()
            
            return jsonify({
                'success': True,
                'message': 'Подписка удалена',
                'deleted_servers': deleted_servers,
                'failed_servers': failed_servers
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/subscription/delete: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500
    
    @app.route('/api/admin/stats', methods=['POST', 'OPTIONS'])
    def api_admin_stats():
        """Статистика для админ-панели"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
        
        try:
            data = request.get_json() or {}
            init_data = data.get('initData') or request.args.get('initData')
            
            if not init_data:
                return jsonify({'error': 'initData is required'}), 400
            
            admin_id = verify_telegram_init_data(init_data)
            if not admin_id:
                return jsonify({'error': 'Invalid authentication'}), 401
            
            if not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
            
            from ...db.subscribers_db import DB_PATH, get_subscription_statistics
            import aiosqlite
            import time
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Получаем статистику подписок
                stats = loop.run_until_complete(get_subscription_statistics())
                
                # Получаем общую статистику пользователей
                async def get_user_stats():
                    async with aiosqlite.connect(DB_PATH) as db:
                        db.row_factory = aiosqlite.Row
                        # Всего пользователей
                        async with db.execute("SELECT COUNT(*) as count FROM users") as cur:
                            row = await cur.fetchone()
                            total_users = row['count'] if row else 0
                        
                        # Пользователей за последние 30 дней
                        thirty_days_ago = int(time.time()) - (30 * 24 * 60 * 60)
                        async with db.execute(
                            "SELECT COUNT(*) as count FROM users WHERE first_seen >= ?",
                            (thirty_days_ago,)
                        ) as cur:
                            row = await cur.fetchone()
                            new_users_30d = row['count'] if row else 0
                        
                        return total_users, new_users_30d
                
                total_users, new_users_30d = loop.run_until_complete(get_user_stats())
                
                # Получаем статистику платежей
                async def get_payment_stats():
                    from ...db.payments_db import get_all_pending_payments
                    async with aiosqlite.connect(DB_PATH) as db:
                        db.row_factory = aiosqlite.Row
                        # Всего платежей
                        async with db.execute("SELECT COUNT(*) as count FROM payments") as cur:
                            row = await cur.fetchone()
                            total_payments = row['count'] if row else 0
                        
                        # Успешных платежей
                        async with db.execute(
                            "SELECT COUNT(*) as count FROM payments WHERE status = 'succeeded'"
                        ) as cur:
                            row = await cur.fetchone()
                            succeeded_payments = row['count'] if row else 0
                        
                        # Сумма успешных платежей (из meta)
                        async with db.execute(
                            "SELECT meta FROM payments WHERE status = 'succeeded'"
                        ) as cur:
                            rows = await cur.fetchall()
                            total_revenue = 0
                            for row in rows:
                                if row['meta']:
                                    try:
                                        import json
                                        meta = json.loads(row['meta']) if isinstance(row['meta'], str) else row['meta']
                                        # Пробуем получить amount или price
                                        amount = meta.get('amount') or meta.get('price', 0)
                                        if isinstance(amount, str):
                                            # Если это строка, пытаемся преобразовать
                                            try:
                                                amount = float(amount)
                                            except (ValueError, TypeError):
                                                amount = 0
                                        if isinstance(amount, (int, float)) and amount > 0:
                                            total_revenue += amount
                                    except Exception as e:
                                        logger.debug(f"Ошибка парсинга meta платежа для дохода: {e}")
                                        pass
                        
                        return total_payments, succeeded_payments, total_revenue
                
                total_payments, succeeded_payments, total_revenue = loop.run_until_complete(get_payment_stats())
            finally:
                loop.close()
            
            return jsonify({
                'success': True,
                'stats': {
                    'users': {
                        'total': total_users,
                        'new_30d': new_users_30d
                    },
                    'subscriptions': {
                        'total': stats.get('total', stats.get('total_subscriptions', 0)),
                        'active': stats.get('active', stats.get('active_subscriptions', 0)),
                        'expired': stats.get('expired', stats.get('expired_subscriptions', 0)),
                        'canceled': stats.get('canceled', 0),
                        'trial': stats.get('trial', 0)
                    },
                    'payments': {
                        'total': total_payments,
                        'succeeded': succeeded_payments,
                        'revenue': round(total_revenue, 2)
                    }
                }
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/stats: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500
    
    @app.route('/api/admin/charts/user-growth', methods=['POST', 'OPTIONS'])
    def api_admin_charts_user_growth():
        """Данные для графика роста пользователей"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
        
        try:
            data = request.get_json() or {}
            init_data = data.get('initData') or request.args.get('initData')
            
            if not init_data:
                return jsonify({'error': 'initData is required'}), 400
            
            admin_id = verify_telegram_init_data(init_data)
            if not admin_id:
                return jsonify({'error': 'Invalid authentication'}), 401
            
            if not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
            
            days = int(data.get('days', 30))  # По умолчанию 30 дней
            
            from ...db.subscribers_db import get_user_growth_data
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                growth_data = loop.run_until_complete(get_user_growth_data(days))
            finally:
                loop.close()
            
            return jsonify({
                'success': True,
                'data': growth_data
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/charts/user-growth: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500
    
    @app.route('/api/admin/charts/server-load', methods=['POST', 'OPTIONS'])
    def api_admin_charts_server_load():
        """Данные для графика нагрузки на серверы"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
        
        try:
            data = request.get_json() or {}
            init_data = data.get('initData') or request.args.get('initData')
            
            if not init_data:
                return jsonify({'error': 'initData is required'}), 400
            
            admin_id = verify_telegram_init_data(init_data)
            if not admin_id:
                return jsonify({'error': 'Invalid authentication'}), 401
            
            if not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
            
            from ...db.subscribers_db import get_server_load_data
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                server_load_data = loop.run_until_complete(get_server_load_data())
                logger.info(f"Получены данные о нагрузке для {len(server_load_data)} серверов")
                if server_load_data:
                    logger.debug(f"Пример данных: {server_load_data[0]}")
            finally:
                loop.close()
            
            if not server_load_data:
                logger.warning("server_load_data пуст, возвращаем пустой ответ")
                return jsonify({
                    'success': True,
                    'data': {
                        'servers': [],
                        'locations': []
                    }
                }), 200, {
                    "Access-Control-Allow-Origin": "*",
                    "Content-Type": "application/json"
                }
            
            # Получаем информацию о серверах (display_name, location) из конфигурации
            def get_server_info():
                try:
                    from ... import bot as bot_module
                    server_manager = getattr(bot_module, 'server_manager', None)
                    if not server_manager:
                        return {}
                    
                    server_info_map = {}
                    for location, servers in server_manager.servers_by_location.items():
                        for server in servers:
                            server_name = server['name']
                            display_name = server['config'].get('display_name', server_name)
                            server_info_map[server_name] = {
                                'display_name': display_name,
                                'location': location
                            }
                    return server_info_map
                except (ImportError, AttributeError):
                    return {}
            
            server_info_map = get_server_info()
            
            # Обогащаем данные информацией о серверах
            enriched_data = []
            for item in server_load_data:
                server_name = item['server_name']
                info = server_info_map.get(server_name, {})
                enriched_data.append({
                    'server_name': server_name,
                    'display_name': info.get('display_name', server_name),
                    'location': info.get('location', 'Unknown'),
                    'online_clients': item.get('online_clients', 0),  # Текущее значение
                    'total_active': item.get('total_active', 0),
                    'offline_clients': item.get('offline_clients', 0),
                    'avg_online_24h': item.get('avg_online_24h', 0),  # Среднее за 24 часа
                    'max_online_24h': item.get('max_online_24h', 0),  # Максимум за 24 часа
                    'min_online_24h': item.get('min_online_24h', 0),  # Минимум за 24 часа
                    'samples_24h': item.get('samples_24h', 0)  # Количество измерений
                })
            
            # Группируем по локациям для дополнительной статистики
            location_stats = {}
            for item in enriched_data:
                location = item['location']
                if location not in location_stats:
                    location_stats[location] = {
                        'location': location,
                        'total_online': 0,
                        'total_active': 0,
                        'servers': []
                    }
                location_stats[location]['total_online'] += item['online_clients']
                location_stats[location]['total_active'] += item['total_active']
                location_stats[location]['servers'].append({
                    'server_name': item['server_name'],
                    'display_name': item['display_name'],
                    'online_clients': item['online_clients'],
                    'total_active': item['total_active']
                })
            
            return jsonify({
                'success': True,
                'data': {
                    'servers': enriched_data,
                    'locations': list(location_stats.values())
                }
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/charts/server-load: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500
    
    @app.route('/api/admin/charts/conversion', methods=['POST', 'OPTIONS'])
    def api_admin_charts_conversion():
        """Данные для графика конверсии"""
        if request.method == 'OPTIONS':
            return ('', 200, {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            })
        
        try:
            data = request.get_json() or {}
            init_data = data.get('initData') or request.args.get('initData')
            
            if not init_data:
                return jsonify({'error': 'initData is required'}), 400
            
            admin_id = verify_telegram_init_data(init_data)
            if not admin_id:
                return jsonify({'error': 'Invalid authentication'}), 401
            
            if not check_admin_access(admin_id):
                return jsonify({'error': 'Access denied'}), 403
            
            days = int(data.get('days', 30))  # По умолчанию 30 дней
            
            from ...db.subscribers_db import get_conversion_data
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                conversion_data = loop.run_until_complete(get_conversion_data(days))
            finally:
                loop.close()
            
            return jsonify({
                'success': True,
                'data': conversion_data
            }), 200, {
                "Access-Control-Allow-Origin": "*",
                "Content-Type": "application/json"
            }
        except Exception as e:
            logger.error(f"Ошибка в /api/admin/charts/conversion: {e}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500
    
    return app


def verify_telegram_init_data(init_data: str) -> str:
    """
    Проверяет initData от Telegram Web App и возвращает user_id если валидно.
    
    Args:
        init_data: Строка initData от Telegram (формат: hash=...&user=...&auth_date=...)
    
    Returns:
        user_id: ID пользователя Telegram, или None если данные невалидны
    """
    try:
        import os
        import hmac
        import hashlib
        import urllib.parse
        import json
        import time
        
        TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
        if not TELEGRAM_TOKEN:
            logger.error("TELEGRAM_TOKEN не найден")
            return None
        
        # Парсим initData
        parsed_data = urllib.parse.parse_qs(init_data)
        
        # Извлекаем hash
        if 'hash' not in parsed_data or not parsed_data['hash']:
            logger.warning("Hash не найден в initData")
            return None
        
        received_hash = parsed_data['hash'][0]
        
        # Извлекаем auth_date
        if 'auth_date' not in parsed_data or not parsed_data['auth_date']:
            logger.warning("auth_date не найден в initData")
            return None
        
        auth_date = int(parsed_data['auth_date'][0])
        
        # Проверяем, что данные не старше 24 часов
        current_time = int(time.time())
        if current_time - auth_date > 24 * 60 * 60:
            logger.warning(f"initData устарел: auth_date={auth_date}, current={current_time}")
            return None
        
        # Создаем секретный ключ из токена бота
        secret_key = hmac.new(
            b"WebAppData",
            TELEGRAM_TOKEN.encode('utf-8'),
            hashlib.sha256
        ).digest()
        
        # Формируем строку для проверки (все параметры кроме hash, отсортированные)
        data_check_string_parts = []
        for key in sorted(parsed_data.keys()):
            if key != 'hash':
                data_check_string_parts.append(f"{key}={parsed_data[key][0]}")
        
        data_check_string = "\n".join(data_check_string_parts)
        
        # Вычисляем hash
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Сравниваем хеши
        if calculated_hash != received_hash:
            logger.warning("Неверный hash в initData")
            return None
        
        # Извлекаем user_id из user
        if 'user' not in parsed_data or not parsed_data['user']:
            logger.warning("user не найден в initData")
            return None
        
        user_data = json.loads(parsed_data['user'][0])
        user_id = str(user_data.get('id'))
        
        if not user_id:
            logger.warning("user_id не найден в user данных")
            return None
        
        logger.info(f"Успешная проверка initData для user_id={user_id}")
        return user_id
        
    except Exception as e:
        logger.error(f"Ошибка при проверке initData: {e}", exc_info=True)
        return None

