"""
Функции инициализации и мониторинга бота
"""
import logging
import datetime
import asyncio
import telegram
from ..db import init_all_db
from ..services import NotificationManager
from ..core.tasks import cleanup_old_payments_task, expired_keys_cleanup_task, sync_db_with_xui_task

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
            'ADMIN_IDS': getattr(bot_module, 'ADMIN_IDS', []),
            'server_manager': getattr(bot_module, 'server_manager', None),
            'new_client_manager': getattr(bot_module, 'new_client_manager', None),
            'subscription_manager': getattr(bot_module, 'subscription_manager', None),
            'sync_manager': getattr(bot_module, 'sync_manager', None),
            'notification_manager': getattr(bot_module, 'notification_manager', None),
        }
    except (ImportError, AttributeError) as e:
        logger.warning(f"Не удалось получить глобальные переменные: {e}")
        return {
            'ADMIN_IDS': [],
            'server_manager': None,
            'new_client_manager': None,
            'subscription_manager': None,
            'sync_manager': None,
            'notification_manager': None,
        }


async def notify_admin(bot, text):
    """Отправляет уведомление всем администраторам с обработкой ошибок и таймаутов"""
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    if not ADMIN_IDS:
        logger.warning("Список администраторов пуст")
        return
        
    for admin_id in ADMIN_IDS:
        try:
            # Используем таймаут для каждой отправки
            async with asyncio.timeout(10):  # 10 секунд на отправку каждому админу
                await bot.send_message(
                    chat_id=admin_id,
                    text=f"❗️[VPNBot ERROR]\n{text}",
                    disable_web_page_preview=True  # Отключаем превью ссылок для ускорения
                )
                logger.info(f"Успешно отправлено уведомление админу {admin_id}")
        except asyncio.TimeoutError:
            logger.error(f"Таймаут при отправке уведомления админу {admin_id}")
        except telegram.error.Forbidden:
            logger.warning(f"Админ {admin_id} заблокировал бота")
        except telegram.error.BadRequest as e:
            if "Chat not found" in str(e):
                logger.warning(f"Админ {admin_id} недоступен: {e}")
            else:
                logger.error(f'BadRequest ошибка отправки уведомления админу {admin_id}: {e}')
        except Exception as e:
            logger.error(f'Ошибка при отправке уведомления админу {admin_id}: {e}')


async def notify_server_issues(bot, server_name, issue_type, details=""):
    """Уведомляет админа о проблемах с серверами"""
    try:
        message = f"🚨 Проблема с сервером {server_name}\n\n"
        message += f"Тип проблемы: {issue_type}\n"
        message += f"Время: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
        message += f"Статус: Требует внимания\n\n"
        
        if details:
            message += f"Детали: {details}\n\n"
        
        message += "Рекомендуемые действия:\n"
        message += "• Проверить доступность сервера\n"
        message += "• Уведомить клиентов о возможных проблемах\n"
        message += "• Проверить логи сервера"
        
        await notify_admin(bot, message)
        logger.warning(f"Отправлено уведомление о проблеме с сервером {server_name}: {issue_type}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления о проблеме с сервером: {e}")


async def server_health_monitor(app):
    """Периодический мониторинг состояния серверов"""
    logger.info("Запуск мониторинга серверов")
    
    globals_dict = get_globals()
    server_manager = globals_dict['server_manager']
    new_client_manager = globals_dict['new_client_manager']
    
    if not server_manager or not new_client_manager:
        logger.warning("server_manager или new_client_manager не доступны, мониторинг будет пропущен")
        return
    
    # Проверяем, есть ли серверы для мониторинга
    if not server_manager.servers or len(server_manager.servers) == 0:
        logger.warning("Нет серверов для мониторинга")
        return
    
    # Словарь для отслеживания предыдущего состояния серверов
    previous_server_status = {}
    
    # При первом запуске ждем немного, чтобы бот успел полностью инициализироваться
    await asyncio.sleep(10)  # Ждем 10 секунд перед первой проверкой
    
    while True:
        try:
            # Проверяем только server_manager (один раз для каждого сервера)
            # new_client_manager использует те же серверы, поэтому не проверяем его отдельно
            # Это уменьшает количество попыток подключения в 2 раза
            health_results = server_manager.check_all_servers_health(force_check=False)
            
            # Если нет результатов (все серверы недоступны), просто логируем и продолжаем
            if not health_results:
                logger.warning("Нет результатов проверки здоровья серверов, все серверы могут быть недоступны")
                await asyncio.sleep(300)
                continue
            
            # Проверяем изменения в состоянии серверов
            current_time = datetime.datetime.now()
            
            for server_name, is_healthy in health_results.items():
                previous_status = previous_server_status.get(server_name, "unknown")
                current_status = "online" if is_healthy else "offline"
                
                # Если статус изменился, отправляем уведомление
                if previous_status != current_status:
                    if current_status == "offline":
                        health_status = server_manager.get_server_health_status()[server_name]
                        last_error = health_status.get("last_error", "Неизвестная ошибка")
                        await notify_server_issues(
                            app.bot, 
                            server_name, 
                            "Сервер недоступен",
                            f"Ошибка: {last_error}"
                        )
                    elif current_status == "online":
                        await notify_server_issues(
                            app.bot, 
                            server_name, 
                            "Сервер восстановлен",
                            "Сервер снова доступен"
                        )
                
                previous_server_status[server_name] = current_status
            
            # Проверяем серверы с длительными проблемами
            for server_name, is_healthy in health_results.items():
                if not is_healthy:
                    health_status = server_manager.get_server_health_status()[server_name]
                    consecutive_failures = health_status.get("consecutive_failures", 0)
                    last_check = health_status.get("last_check")
                    
                    # Если сервер недоступен более 15 минут (3 проверки по 5 минут)
                    if consecutive_failures >= 3 and last_check:
                        time_since_last_check = current_time - last_check
                        if time_since_last_check.total_seconds() > 900:  # 15 минут
                            await notify_server_issues(
                                app.bot, 
                                server_name, 
                                "Длительная недоступность",
                                f"Сервер недоступен более 15 минут. Неудачных попыток: {consecutive_failures}"
                            )
            
            # Логируем статус всех серверов
            logger.info(f"Статус серверов: {health_results}")
            
        except Exception as e:
            logger.error(f"Ошибка в мониторинге серверов: {e}")
        
        # Ждем 5 минут до следующей проверки
        await asyncio.sleep(300)


async def on_startup(app):
    """Инициализация бота при запуске"""
    globals_dict = get_globals()
    server_manager = globals_dict['server_manager']
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    # Устанавливаем глобальную переменную notification_manager в bot.py
    try:
        import sys
        import importlib
        if 'bot.bot' in sys.modules:
            bot_module = sys.modules['bot.bot']
        else:
            bot_module = importlib.import_module('bot.bot')
        
        # Инициализируем менеджер уведомлений
        logger.info("=== НАЧАЛО ИНИЦИАЛИЗАЦИИ БОТА ===")
        
        await init_all_db()  # Инициализирует все базы данных
        
        # Инициализируем менеджер уведомлений
        logger.info("Инициализация менеджера уведомлений...")
        notification_manager = NotificationManager(app.bot, server_manager, ADMIN_IDS)
        await notification_manager.initialize()
        await notification_manager.start()
        
        # Сохраняем в глобальную переменную bot.py
        bot_module.notification_manager = notification_manager
        
        logger.info("Менеджер уведомлений запущен")
        
        logger.info("=== ИНИЦИАЛИЗАЦИЯ БОТА ЗАВЕРШЕНА ===")
        
        # Запускаем остальные задачи
        asyncio.create_task(server_health_monitor(app))
        asyncio.create_task(cleanup_old_payments_task())
        # Запускаем задачу очистки просроченных ключей
        asyncio.create_task(expired_keys_cleanup_task())
        # Запускаем задачу синхронизации БД с X-UI
        asyncio.create_task(sync_db_with_xui_task())
        
    except Exception as e:
        logger.error(f"Ошибка инициализации бота: {e}")
        raise

