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
    
    return app

