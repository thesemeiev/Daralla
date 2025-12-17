"""
Периодические задачи очистки данных
"""
import logging
import datetime
import json
import asyncio
from ..db import cleanup_expired_pending_payments, cleanup_old_payments, get_payment_by_id
from ..db.subscribers_db import get_all_active_subscriptions, update_subscription_status

logger = logging.getLogger(__name__)


def get_globals():
    """Получает глобальные переменные из bot.py"""
    try:
        import sys
        import importlib
        # Пытаемся получить модуль bot.bot
        if 'bot.bot' in sys.modules:
            bot_module = sys.modules['bot.bot']
        else:
            # Если модуль еще не загружен, импортируем его
            bot_module = importlib.import_module('bot.bot')
        
        return {
            'extension_keys_cache': getattr(bot_module, 'extension_keys_cache', {}),
            'extension_messages': getattr(bot_module, 'extension_messages', {}),
            'server_manager': getattr(bot_module, 'server_manager', None),
            'new_client_manager': getattr(bot_module, 'new_client_manager', None),
            'subscription_manager': getattr(bot_module, 'subscription_manager', None),
            'sync_manager': getattr(bot_module, 'sync_manager', None),
            'notification_manager': getattr(bot_module, 'notification_manager', None),
            'notify_admin': getattr(bot_module, 'notify_admin', None),
            'app': getattr(bot_module, 'app', None),
        }
    except (ImportError, AttributeError) as e:
        logger.warning(f"Не удалось получить глобальные переменные: {e}")
        return {
            'extension_keys_cache': {},
            'extension_messages': {},
            'server_manager': None,
            'new_client_manager': None,
            'subscription_manager': None,
            'sync_manager': None,
            'notification_manager': None,
            'notify_admin': None,
            'app': None,
        }


async def cleanup_old_payments_task():
    """Периодическая очистка старых платежей и данных"""
    while True:
        try:
            logger.info("🧹 Запуск периодической очистки данных")
            
            # Очищаем просроченные pending платежи
            expired_count = await cleanup_expired_pending_payments(minutes_old=20)
            if expired_count > 0:
                logger.info(f"🧹 Очистка: Удалено {expired_count} просроченных pending платежей")
            
            # Очищаем старые записи платежей
            old_count = await cleanup_old_payments(days_old=7)
            if old_count > 0:
                logger.info(f"🧹 Очистка: Удалено {old_count} старых записей платежей")
            
            # Получаем глобальные переменные
            globals_dict = get_globals()
            extension_keys_cache = globals_dict['extension_keys_cache']
            
            # Очищаем кэш extension_keys_cache от старых записей
            current_time = datetime.datetime.now().timestamp()
            keys_to_remove = []
            for short_id, key_info in list(extension_keys_cache.items()):
                # Приводим к единому формату: если значение не словарь, удаляем как устаревшее
                if not isinstance(key_info, dict):
                    keys_to_remove.append(short_id)
                    continue
                # Если запись старше 1 часа, удаляем её
                if current_time - key_info.get('created_at', 0) > 3600:
                    keys_to_remove.append(short_id)
            
            for short_id in keys_to_remove:
                extension_keys_cache.pop(short_id, None)
            
            if keys_to_remove:
                logger.info(f"🧹 Очистка: Удалено {len(keys_to_remove)} старых записей из extension_keys_cache")
            
            # Очищаем истекшие подписки
            expired_subscriptions_count = await cleanup_expired_subscriptions()
            if expired_subscriptions_count > 0:
                logger.info(f"🧹 Очистка: Обновлено {expired_subscriptions_count} истекших подписок")
            
            logger.info("🧹 Периодическая очистка завершена")
            
        except Exception as e:
            logger.error(f"Ошибка в периодической очистке: {e}")
        
        # Ждем 1 час до следующей очистки
        await asyncio.sleep(3600)


async def expired_keys_cleanup_task():
    """Периодическая задача для очистки просроченных ключей"""
    logger.info("Запуск периодической задачи очистки просроченных ключей")
    while True:
        try:
            await auto_cleanup_expired_keys()
            # Ждем 12 часов перед следующей проверкой
            await asyncio.sleep(12 * 60 * 60)
        except Exception as e:
            logger.error(f"Ошибка в периодической задаче очистки ключей: {e}")
            # В случае ошибки ждем 1 час перед повторной попыткой
            await asyncio.sleep(60 * 60)


async def auto_cleanup_expired_keys():
    """Автоматически удаляет просроченные ключи со всех серверов"""
    logger.info("Запуск автоматической очистки просроченных ключей...")
    
    try:
        # Получаем глобальные переменные
        globals_dict = get_globals()
        server_manager = globals_dict['server_manager']
        notification_manager = globals_dict['notification_manager']
        notify_admin = globals_dict['notify_admin']
        app = globals_dict['app']
        extension_keys_cache = globals_dict['extension_keys_cache']
        extension_messages = globals_dict['extension_messages']
        
        if not server_manager:
            logger.error("server_manager не доступен")
            return 0
        
        # app может быть недоступен при первом запуске, но это не критично для очистки
        if not app:
            logger.warning("app не доступен - очистка будет выполнена без уведомлений пользователям")
            # Продолжаем работу, но без отправки уведомлений
        
        now_ms = int(datetime.datetime.now().timestamp() * 1000)
        # 3 дня после истечения = 3 * 24 * 60 * 60 * 1000 миллисекунд
        threshold_ms = now_ms - 3 * 24 * 60 * 60 * 1000
        total_deleted_count = 0
        
        # Проверяем, есть ли хотя бы один доступный сервер
        available_servers_count = 0
        for server in server_manager.servers:
            if server.get("x3") is not None:
                try:
                    # Проверяем доступность сервера
                    if server_manager.check_server_health(server["name"]):
                        available_servers_count += 1
                except Exception:
                    pass
        
        if available_servers_count == 0:
            logger.info("Нет доступных серверов для очистки просроченных ключей. Ожидаем восстановления серверов...")
            return 0
        
        # Очищаем все серверы
        for server in server_manager.servers:
            try:
                xui = server["x3"]
                if xui is None:
                    logger.warning(f"Сервер {server['name']} недоступен, пропускаем очистку")
                    continue
                
                # Дополнительная проверка доступности перед операциями
                try:
                    if not server_manager.check_server_health(server["name"]):
                        logger.warning(f"Сервер {server['name']} недоступен по проверке здоровья, пропускаем очистку")
                        continue
                except Exception as health_check_error:
                    logger.warning(f"Ошибка проверки здоровья сервера {server['name']}: {health_check_error}, пропускаем очистку")
                    continue
                
                deleted_count = 0
                try:
                    inbounds = xui.list()['obj']
                except Exception as list_error:
                    logger.warning(f"Ошибка получения списка клиентов с сервера {server['name']}: {list_error}, пропускаем очистку")
                    continue
                
                for inbound in inbounds:
                    settings = json.loads(inbound['settings'])
                    clients_to_delete = []
                    
                    # Собираем список клиентов для удаления
                    for client in settings.get("clients", []):
                        expiry = client.get('expiryTime', 0)
                        email = client.get('email', '')
                        
                        # Проверяем, что ключ просрочен более 3 дней
                        if expiry and expiry < threshold_ms:
                            # Удаляем только пользовательские ключи (с подчеркиванием)
                            if '_' in email:
                                clients_to_delete.append(client)
                    
                    # Удаляем найденных клиентов
                    for client in clients_to_delete:
                        try:
                            client_id = client.get('id')
                            inbound_id = inbound['id']
                            email = client.get('email', '')
                            
                            # Извлекаем user_id из email (формат: user_id_email@domain.com)
                            user_id = None
                            if '_' in email:
                                user_id = email.split('_')[0]
                            
                            # Формируем URL для удаления
                            url = f"{xui.host}/panel/api/inbounds/{inbound_id}/delClient/{client_id}"
                            logger.info(f"Автоудаление просроченного ключа: inbound_id={inbound_id}, client_id={client_id}, email={email}")
                            
                            # Отправляем запрос на удаление
                            result = xui.ses.post(url)
                            if getattr(result, 'status_code', None) == 200:
                                deleted_count += 1
                                total_deleted_count += 1
                                
                                # Вычисляем, сколько дней назад истек ключ
                                expiry_date = datetime.datetime.fromtimestamp(client.get('expiryTime', 0) / 1000)
                                days_expired = (datetime.datetime.now() - expiry_date).days
                                
                                logger.info(f'Автоудален просроченный ключ: {email} с сервера {server["name"]} (истек {days_expired} дней назад)')
                                
                                # Очищаем связанные данные из кэшей
                                try:
                                    # Очищаем extension_keys_cache
                                    keys_to_remove = []
                                    for short_id, key_email in extension_keys_cache.items():
                                        if key_email == email:
                                            keys_to_remove.append(short_id)
                                    for short_id in keys_to_remove:
                                        extension_keys_cache.pop(short_id, None)
                                    
                                    if keys_to_remove:
                                        logger.info(f"Очищено {len(keys_to_remove)} записей из extension_keys_cache для удаленного ключа {email}")
                                    
                                    # Очищаем extension_messages для удаленного ключа
                                    extension_keys_to_remove = []
                                    for payment_id, (chat_id, msg_id) in list(extension_messages.items()):
                                        try:
                                            payment_info = await get_payment_by_id(payment_id)
                                            if payment_info and payment_info.get('meta'):
                                                meta = payment_info['meta'] if isinstance(payment_info['meta'], dict) else json.loads(payment_info['meta'])
                                                if meta.get('extension_key_email') == email:
                                                    extension_keys_to_remove.append(payment_id)
                                        except Exception as e:
                                            logger.warning(f"Ошибка при проверке связи платежа {payment_id} с ключом {email}: {e}")
                                    
                                    for payment_id in extension_keys_to_remove:
                                        extension_messages.pop(payment_id, None)
                                    
                                    if extension_keys_to_remove:
                                        logger.info(f"Очищено {len(extension_keys_to_remove)} записей из extension_messages для удаленного ключа {email}")
                                    
                                    # Очищаем уведомления для удаленного ключа
                                    if user_id:
                                        try:
                                            # Используем глобальный notification_manager, инициализируемый в on_startup
                                            if notification_manager:
                                                await notification_manager.clear_key_notifications(user_id, email)
                                        except Exception as e:
                                            logger.error(f"Ошибка очистки уведомлений для удаленного ключа {email}: {e}")
                                            
                                except Exception as e:
                                    logger.error(f"Ошибка очистки кэшей при удалении ключа {email}: {e}")
                                
                                # Отправляем уведомление пользователю об удалении ключа
                                if user_id:
                                    try:
                                        if notification_manager:
                                            # Используем асинхронный таймаут
                                            async with asyncio.timeout(30):  # 30 секунд таймаут
                                                await notification_manager.send_key_deletion_notification(
                                                    user_id=user_id,
                                                    email=email,
                                                    server_name=server["name"],
                                                    days_expired=days_expired
                                                )
                                                logger.info(f"Отправлено уведомление об удалении ключа пользователю {user_id}")
                                    except asyncio.TimeoutError:
                                        logger.error(f"Таймаут при отправке уведомления об удалении пользователю {user_id}")
                                    except Exception as e:
                                        logger.error(f"Ошибка отправки уведомления об удалении пользователю {user_id}: {e}")
                            else:
                                logger.warning(f"Не удалось удалить ключ {email}: status_code={getattr(result, 'status_code', None)}")
                                
                        except Exception as e:
                            logger.error(f"Ошибка при автоудалении ключа {client.get('email', 'unknown')}: {e}")
                            continue
                
                if deleted_count > 0:
                    logger.info(f"Автоудалено {deleted_count} просроченных ключей с сервера {server['name']}")
                    
            except Exception as e:
                logger.error(f"Ошибка при автоочистке сервера {server['name']}: {e}")
                # Уведомляем админа о критической ошибке автоочистки
                if notify_admin and app:
                    await notify_admin(app.bot, f"КРИТИЧЕСКАЯ ОШИБКА: Ошибка при автоочистке сервера:\nСервер: {server['name']}\nОшибка: {str(e)}")
                continue
        
        logger.info(f"Автоочистка завершена. Всего удалено просроченных ключей: {total_deleted_count}")
        return total_deleted_count
        
    except Exception as e:
        logger.error(f"Критическая ошибка в auto_cleanup_expired_keys: {e}")
        # Уведомляем админа о критической ошибке автоочистки
        globals_dict = get_globals()
        notify_admin = globals_dict['notify_admin']
        app = globals_dict['app']
        if notify_admin and app:
            await notify_admin(app.bot, f"КРИТИЧЕСКАЯ ОШИБКА: Критическая ошибка в auto_cleanup_expired_keys:\nОшибка: {str(e)}")
        return 0


async def cleanup_expired_subscriptions():
    """Автоматически обновляет статус истекших подписок"""
    try:
        import time
        current_time = int(time.time())
        
        subscriptions = await get_all_active_subscriptions()
        expired_count = 0
        
        for sub in subscriptions:
            if sub['expires_at'] < current_time:
                # Подписка истекла, обновляем статус
                await update_subscription_status(sub['id'], 'expired')
                expired_count += 1
                logger.info(f"Подписка {sub['id']} для пользователя {sub['user_id']} помечена как истекшая")
        
        return expired_count
        
    except Exception as e:
        logger.error(f"Ошибка в cleanup_expired_subscriptions: {e}")
        return 0


async def sync_db_with_xui_task():
    """
    Периодическая задача синхронизации БД подписок с X-UI серверами.
    Запускается каждые 6 часов для предотвращения рассинхронизации.
    """
    logger.info("Запуск периодической синхронизации БД с X-UI")
    while True:
        try:
            # Ждем 6 часов перед первой синхронизацией (чтобы не нагружать при старте)
            await asyncio.sleep(6 * 60 * 60)
            
            # Получаем SyncManager из глобальных переменных
            globals_dict = get_globals()
            sync_manager = globals_dict.get('sync_manager')
            
            if not sync_manager:
                logger.warning("sync_manager не доступен, пропускаем синхронизацию")
                continue
            
            # Выполняем синхронизацию всех подписок
            stats = await sync_manager.sync_all_subscriptions()
            
            # Логируем результаты
            if stats['total_errors'] > 0:
                logger.warning(
                    f"Синхронизация завершена с ошибками: "
                    f"проверено {stats['subscriptions_checked']} подписок, "
                    f"синхронизировано {stats['subscriptions_synced']}, "
                    f"ошибок {stats['total_errors']}"
                )
            else:
                logger.info(
                    f"Синхронизация успешно завершена: "
                    f"проверено {stats['subscriptions_checked']} подписок, "
                    f"все синхронизированы"
                )
            
            # Ищем orphaned клиентов (клиенты на серверах без записи в БД)
            try:
                orphaned = await sync_manager.find_orphaned_clients()
                if orphaned:
                    logger.warning(
                        f"Найдено {len(orphaned)} orphaned клиентов на серверах "
                        f"(клиенты без записи в БД подписок)"
                    )
                    # Логируем первые 10 для примера
                    for orphan in orphaned[:10]:
                        logger.warning(
                            f"Orphaned клиент: {orphan['client_email']} на сервере {orphan['server_name']}"
                        )
            except Exception as e:
                logger.error(f"Ошибка поиска orphaned клиентов: {e}")
            
        except Exception as e:
            logger.error(f"Ошибка в задаче синхронизации БД с X-UI: {e}")
            # В случае ошибки ждем 1 час перед повторной попыткой
            await asyncio.sleep(60 * 60)

