"""
Фоновые задачи бота
"""
import asyncio
import logging

logger = logging.getLogger(__name__)

def _use_xui_sync():
    """True если нужна синхронизация с X-UI (не используется Remnawave)."""
    try:
        from ..services.remnawave_service import is_remnawave_configured
        return not is_remnawave_configured()
    except Exception:
        return True


async def start_background_tasks(sync_manager, subscription_manager, notification_manager, server_manager=None):
    """Запускает все фоновые задачи. sync_manager/subscription_manager могут быть None (режим Remnawave)."""
    logger.info("🚀 Запуск цикла фоновых задач...")

    # 1. Задача синхронизации X-UI (не запускается при Remnawave или при sync_manager=None)
    asyncio.create_task(sync_task_loop(sync_manager))

    # 2. Задача проверки истекающих подписок для уведомлений (каждые 30 минут)
    asyncio.create_task(notifications_task_loop(notification_manager))

    # 3. Задача очистки старых платежей (каждый час)
    asyncio.create_task(payments_cleanup_loop())

    # 4. Снимки нагрузки на X-UI серверы (только при использовании X-UI)
    if server_manager and _use_xui_sync():
        asyncio.create_task(server_load_snapshot_loop(server_manager))


async def sync_task_loop(sync_manager):
    """Цикл синхронизации данных с X-UI. При Remnawave (sync_manager=None) только пауза."""
    while True:
        try:
            if sync_manager is None or not _use_xui_sync():
                logger.debug("Remnawave включён — синхронизация X-UI пропущена")
            else:
                await sync_manager.run_sync()
        except Exception as e:
            logger.error("Ошибка в цикле синхронизации: %s", e)
        await asyncio.sleep(6 * 3600)

async def notifications_task_loop(notification_manager):
    """Цикл уведомлений"""
    while True:
        try:
            # Метод внутри сам проверяет, кому пора слать
            await notification_manager._check_expiring_subscriptions()
        except Exception as e:
            logger.error(f"Ошибка в цикле уведомлений: {e}")
            
        # Раз в 30 минут
        await asyncio.sleep(1800)

async def payments_cleanup_loop():
    """Очистка просроченных платежей"""
    from ..db import cleanup_expired_pending_payments
    while True:
        try:
            count = await cleanup_expired_pending_payments(minutes_old=60)
            if count > 0:
                logger.info(f"Очищено {count} просроченных платежей")
        except Exception as e:
            logger.error(f"Ошибка в очистке платежей: {e}")
            
        # Раз в час
        await asyncio.sleep(3600)

async def server_load_snapshot_loop(server_manager):
    """Периодическое сохранение снимков нагрузки на серверы для расчета средних значений"""
    from ..db import save_server_load_snapshot, cleanup_old_server_load_history
    
    # Ждем 30 секунд после запуска бота, чтобы все инициализировалось
    await asyncio.sleep(30)
    
    logger.info("📊 Запуск задачи сохранения снимков нагрузки на серверы")
    
    # Очищаем старую историю при запуске (старше 7 дней)
    try:
        await cleanup_old_server_load_history(days=7)
    except Exception as e:
        logger.error(f"Ошибка очистки старой истории нагрузки: {e}")
    
    snapshot_interval = 10 * 60  # 10 минут
    cleanup_interval = 24 * 3600  # 24 часа
    last_cleanup = 0
    
    while True:
        try:
            if not server_manager or not hasattr(server_manager, 'servers'):
                logger.warning("server_manager недоступен для сохранения снимков нагрузки")
                await asyncio.sleep(snapshot_interval)
                continue
            
            servers_saved = 0
            servers_failed = 0
            
            # Проходим по всем серверам и сохраняем снимки
            for server in server_manager.servers:
                server_name = server.get("name", "Unknown")
                xui = server.get("x3")
                
                if not xui:
                    continue
                
                try:
                    # Получаем текущую нагрузку на сервер
                    total_active, online_count, offline_count = xui.get_online_clients_count()
                    
                    # Сохраняем снимок
                    await save_server_load_snapshot(
                        server_name=server_name,
                        online_clients=online_count,
                        total_active=total_active,
                        offline_clients=offline_count
                    )
                    
                    servers_saved += 1
                    logger.debug(f"Сохранен снимок нагрузки для {server_name}: онлайн={online_count}, активных={total_active}")
                    
                except Exception as e:
                    servers_failed += 1
                    logger.warning(f"Ошибка сохранения снимка нагрузки для {server_name}: {e}")
            
            if servers_saved > 0:
                logger.info(f"📊 Сохранено {servers_saved} снимков нагрузки на серверы")
            
            # Периодически очищаем старую историю (раз в 24 часа)
            import time
            current_time = time.time()
            if current_time - last_cleanup >= cleanup_interval:
                try:
                    await cleanup_old_server_load_history(days=7)
                    last_cleanup = current_time
                    logger.info("Очищена старая история нагрузки на серверы (старше 7 дней)")
                except Exception as e:
                    logger.error(f"Ошибка очистки истории нагрузки: {e}")
            
        except Exception as e:
            logger.error(f"Ошибка в цикле сохранения снимков нагрузки: {e}", exc_info=True)
        
        # Раз в 10 минут
        await asyncio.sleep(snapshot_interval)
