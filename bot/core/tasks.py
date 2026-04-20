"""
Фоновые задачи бота
"""
import asyncio
import logging
import os

from bot.web.observability import inc_metric

logger = logging.getLogger(__name__)


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Переменная %s=%r не число, используется %s", name, raw, default)
        return default


async def start_background_tasks(sync_manager, subscription_manager, notification_manager, server_manager=None):
    """Запускает все фоновые задачи"""
    logger.info("🚀 Запуск цикла фоновых задач...")
    
    # 1. Полный sync (интервал DARALLA_SYNC_INTERVAL_SECONDS, по умолчанию 6 ч)
    asyncio.create_task(sync_task_loop(sync_manager))

    catchup_sec = _int_env("DARALLA_CLIENT_CATCHUP_INTERVAL_SECONDS", 15 * 60)
    if catchup_sec > 0:
        asyncio.create_task(client_catchup_loop(sync_manager))
        logger.info(
            "Фоновый догон клиентов на панелях: каждые %s с (~%.1f мин), "
            "DARALLA_CLIENT_CATCHUP_INTERVAL_SECONDS (0 = выключить)",
            catchup_sec,
            catchup_sec / 60,
        )
    else:
        logger.info("Фоновый догон клиентов выключен (DARALLA_CLIENT_CATCHUP_INTERVAL_SECONDS=0)")
    
    # 2. Задача проверки истекающих подписок для уведомлений (каждые 30 минут)
    asyncio.create_task(notifications_task_loop(notification_manager))
    
    # 3. Задача очистки старых платежей (каждый час)
    asyncio.create_task(payments_cleanup_loop())
    
    # 4. Задача сохранения снимков нагрузки на серверы (каждые 10 минут)
    if server_manager:
        asyncio.create_task(server_load_snapshot_loop(server_manager))

async def sync_task_loop(sync_manager):
    """Полный sync: статусы, cleanup просроченных, клиенты на панелях, сироты."""
    interval = max(60, _int_env("DARALLA_SYNC_INTERVAL_SECONDS", 6 * 3600))
    logger.info(
        "Полный sync (run_sync): каждые %s с (~%.2f ч), DARALLA_SYNC_INTERVAL_SECONDS",
        interval,
        interval / 3600,
    )
    while True:
        try:
            await sync_manager.run_sync()
            inc_metric("background_task_success_total", task="full_sync")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Ошибка в цикле синхронизации: %s", e, exc_info=True)
            inc_metric("background_task_error_total", task="full_sync")

        await asyncio.sleep(interval)


async def client_catchup_loop(sync_manager):
    """Лёгкий периодический догон только ensure клиентов (без полной уборки)."""
    interval = max(60, _int_env("DARALLA_CLIENT_CATCHUP_INTERVAL_SECONDS", 15 * 60))
    logger.info(
        "Догон клиентов (sync_clients_from_db_only): каждые %s с (~%.1f мин)",
        interval,
        interval / 60,
    )
    await asyncio.sleep(90)
    while True:
        try:
            await sync_manager.sync_clients_from_db_only()
            inc_metric("background_task_success_total", task="client_catchup")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Ошибка в цикле догона клиентов: %s", e, exc_info=True)
            inc_metric("background_task_error_total", task="client_catchup")
        await asyncio.sleep(interval)

async def notifications_task_loop(notification_manager):
    """Цикл уведомлений"""
    while True:
        try:
            # Метод внутри сам проверяет, кому пора слать
            await notification_manager._check_expiring_subscriptions()
            inc_metric("background_task_success_total", task="notifications")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Ошибка в цикле уведомлений: {e}")
            inc_metric("background_task_error_total", task="notifications")
            
        # Раз в 30 минут
        await asyncio.sleep(1800)

async def payments_cleanup_loop():
    """Очистка просроченных платежей (pending → expired) и старых записей (раз в сутки)"""
    from ..db import cleanup_expired_pending_payments, cleanup_old_payments
    iteration = 0
    while True:
        try:
            count = await cleanup_expired_pending_payments(minutes_old=60)
            inc_metric("background_task_success_total", task="payments_cleanup")
            if count > 0:
                logger.info(f"Очищено {count} просроченных платежей")
            # Раз в 24 часа удаляем старые не-pending платежи (старше 30 дней)
            iteration += 1
            if iteration >= 24:
                iteration = 0
                deleted = await cleanup_old_payments(days=30)
                if deleted > 0:
                    logger.info(f"Удалено {deleted} старых записей платежей (старше 30 дней)")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Ошибка в очистке платежей: {e}")
            inc_metric("background_task_error_total", task="payments_cleanup")
            
        # Раз в час
        await asyncio.sleep(3600)

async def server_load_snapshot_loop(server_manager):
    """Периодическое сохранение снимков нагрузки на серверы для расчета средних значений"""
    from ..db.servers_db import save_server_load_snapshot, cleanup_old_server_load_history
    
    # Ждем 30 секунд после запуска бота, чтобы все инициализировалось
    await asyncio.sleep(30)
    
    logger.info("📊 Запуск задачи сохранения снимков нагрузки на серверы")
    
    # Очищаем старую историю при запуске (старше 7 дней)
    try:
        await cleanup_old_server_load_history(days=7)
    except asyncio.CancelledError:
        raise
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
                    total_active, online_count, offline_count = await xui.get_online_clients_count()
                    
                    # Сохраняем снимок
                    await save_server_load_snapshot(
                        server_name=server_name,
                        online_clients=online_count,
                        total_active=total_active,
                        offline_clients=offline_count
                    )
                    
                    servers_saved += 1
                    inc_metric("background_task_success_total", task="server_load_snapshot")
                    logger.debug(f"Сохранен снимок нагрузки для {server_name}: онлайн={online_count}, активных={total_active}")
                    
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    servers_failed += 1
                    inc_metric("background_task_error_total", task="server_load_snapshot")
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
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Ошибка очистки истории нагрузки: {e}")
            
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Ошибка в цикле сохранения снимков нагрузки: {e}", exc_info=True)
        
        # Раз в 10 минут
        await asyncio.sleep(snapshot_interval)
