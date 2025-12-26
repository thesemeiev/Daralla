"""
Функции инициализации и мониторинга бота
"""
import logging
import datetime
import asyncio
import telegram
from ..db import init_all_db
from ..services import NotificationManager

logger = logging.getLogger(__name__)


async def notify_admin(bot, admin_ids, text):
    """Отправляет уведомление всем администраторам"""
    if not admin_ids:
        logger.warning("Список администраторов пуст")
        return
        
    for admin_id in admin_ids:
        try:
            async with asyncio.timeout(10):
                await bot.send_message(
                    chat_id=admin_id,
                    text=f"❗️[VPNBot ERROR]\n{text}",
                    disable_web_page_preview=True
                )
                logger.info(f"Успешно отправлено уведомление админу {admin_id}")
        except Exception as e:
            logger.error(f'Ошибка при отправке уведомления админу {admin_id}: {e}')


async def notify_server_issues(bot, admin_ids, server_name, issue_type, details=""):
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
        message += "• Проверить логи сервера"
        
        await notify_admin(bot, admin_ids, message)
        
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления о проблеме с сервером: {e}")


async def server_health_monitor(app, server_manager, admin_ids):
    """Периодический мониторинг состояния серверов"""
    logger.info("Запуск мониторинга серверов")
    
    if not server_manager:
        logger.warning("server_manager не доступен, мониторинг пропущен")
        return
    
    previous_server_status = {}
    await asyncio.sleep(10)
    
    while True:
        try:
            health_results = server_manager.check_all_servers_health(force_check=False)
            
            if not health_results:
                await asyncio.sleep(300)
                continue
            
            current_time = datetime.datetime.now()
            
            for server_name, is_healthy in health_results.items():
                previous_status = previous_server_status.get(server_name, "unknown")
                current_status = "online" if is_healthy else "offline"
                
                if previous_status != current_status:
                    if current_status == "offline":
                        health_status = server_manager.get_server_health_status()[server_name]
                        last_error = health_status.get("last_error", "Неизвестная ошибка")
                        await notify_server_issues(
                            app.bot, admin_ids,
                            server_name, 
                            "Сервер недоступен",
                            f"Ошибка: {last_error}"
                        )
                    elif current_status == "online":
                        await notify_server_issues(
                            app.bot, admin_ids,
                            server_name, 
                            "Сервер восстановлен",
                            "Сервер снова доступен"
                        )
                
                previous_server_status[server_name] = current_status
            
            # Длительные проблемы
            for server_name, is_healthy in health_results.items():
                if not is_healthy:
                    health_status = server_manager.get_server_health_status()[server_name]
                    if health_status.get("consecutive_failures", 0) >= 3:
                        await notify_server_issues(
                            app.bot, admin_ids,
                            server_name, 
                            "Длительная недоступность",
                            "Сервер недоступен более 15 минут"
                        )
            
        except Exception as e:
            logger.error(f"Ошибка в мониторинге серверов: {e}")
        
        await asyncio.sleep(300)


async def on_startup(app):
    """Инициализация бота при запуске"""
    try:
        import sys
        # Получаем объекты напрямую из модуля bot.bot
        bot_module = sys.modules.get('bot.bot')
        if not bot_module:
            import importlib
            bot_module = importlib.import_module('bot.bot')
        
        server_manager = getattr(bot_module, 'server_manager', None)
        subscription_manager = getattr(bot_module, 'subscription_manager', None)
        sync_manager = getattr(bot_module, 'sync_manager', None)
        admin_ids = getattr(bot_module, 'ADMIN_IDS', [])
        
        logger.info("=== НАЧАЛО ИНИЦИАЛИЗАЦИИ БОТА ===")
        
        # 1. Инициализация БД
        await init_all_db()
        
        # 2. Инициализация и запуск менеджера уведомлений
        notification_manager = NotificationManager(app.bot, server_manager, admin_ids)
        await notification_manager.initialize()
        await notification_manager.start()
        bot_module.notification_manager = notification_manager
        
        logger.info("Менеджер уведомлений запущен")
        logger.info("=== ИНИЦИАЛИЗАЦИЯ БОТА ЗАВЕРШЕНА ===")
        
        # 3. Запуск фоновых задач (единый цикл)
        from .tasks import start_background_tasks
        await start_background_tasks(sync_manager, subscription_manager, notification_manager, server_manager)
        
        # 4. Запуск мониторинга здоровья серверов
        asyncio.create_task(server_health_monitor(app, server_manager, admin_ids))
        
        # 5. Первоначальная синхронизация через 30 секунд
        async def initial_sync():
            await asyncio.sleep(30)
            if subscription_manager:
                logger.info("Выполнение первоначальной синхронизации серверов...")
                await subscription_manager.sync_servers_with_config(auto_create_clients=True)
        
        asyncio.create_task(initial_sync())
        
    except Exception as e:
        logger.error(f"Ошибка инициализации бота: {e}")
        raise
