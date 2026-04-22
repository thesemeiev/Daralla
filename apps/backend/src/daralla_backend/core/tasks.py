"""
Фоновые задачи бота
"""
import asyncio
import logging
import os

from daralla_backend.core.retention_policy import get_retention_policy
from daralla_backend.utils.logging_helpers import log_event
from daralla_backend.web.observability import inc_metric

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

    # 5. Суточный maintenance: retention sweep + рост таблиц
    asyncio.create_task(retention_maintenance_loop())

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
    policy = get_retention_policy()
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
                deleted = await cleanup_old_payments(
                    days=policy.payments_retention_days,
                    dry_run=policy.dry_run,
                )
                if deleted > 0:
                    mode = "dry-run candidates" if policy.dry_run else "deleted"
                    logger.info(
                        "Payments retention cleanup: %s %s rows (older than %s days)",
                        mode,
                        deleted,
                        policy.payments_retention_days,
                    )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Ошибка в очистке платежей: {e}")
            inc_metric("background_task_error_total", task="payments_cleanup")
            
        # Раз в час
        await asyncio.sleep(3600)

async def server_load_snapshot_loop(server_manager):
    """Периодическое сохранение снимков нагрузки на серверы для расчета средних значений"""
    from ..db.servers_db import (
        save_server_load_snapshot,
        cleanup_old_server_load_history_with_policy,
    )
    policy = get_retention_policy()
    
    # Ждем 30 секунд после запуска бота, чтобы все инициализировалось
    await asyncio.sleep(30)
    
    logger.info("📊 Запуск задачи сохранения снимков нагрузки на серверы")
    
    # Очищаем старую историю при запуске (старше 7 дней)
    try:
        await cleanup_old_server_load_history_with_policy(
            days=policy.server_load_retention_days,
            dry_run=policy.dry_run,
        )
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
                    cleaned = await cleanup_old_server_load_history_with_policy(
                        days=policy.server_load_retention_days,
                        dry_run=policy.dry_run,
                    )
                    last_cleanup = current_time
                    mode = "dry-run candidates" if policy.dry_run else "cleaned"
                    if cleaned > 0:
                        logger.info(
                            "Server load retention: %s %s rows older than %s days",
                            mode,
                            cleaned,
                            policy.server_load_retention_days,
                        )
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


async def retention_maintenance_loop():
    """
    Суточная задача:
    - cleanup deleted subscriptions / inactive users / old event raw / old daily aggregates;
    - лог размеров ключевых таблиц для контроля роста БД.
    """
    from ..db import (
        cleanup_deleted_subscriptions,
        cleanup_inactive_users,
        cleanup_old_daily_aggregates,
        get_table_row_counts,
    )
    from ..events.db.queries import cleanup_old_event_raw

    # Даем приложению и миграциям закончить старт
    await asyncio.sleep(120)
    while True:
        policy = get_retention_policy()
        try:
            sub_deleted = await cleanup_deleted_subscriptions(
                days=policy.deleted_subscriptions_retention_days,
                dry_run=policy.dry_run,
            )
            users_deleted = await cleanup_inactive_users(
                days=policy.auto_delete_inactive_users_days,
                dry_run=policy.dry_run,
            )
            events_deleted = await cleanup_old_event_raw(
                days=policy.events_raw_retention_days,
                dry_run=policy.dry_run,
            )
            agg_deleted = await cleanup_old_daily_aggregates(
                days=policy.daily_agg_retention_days,
                dry_run=policy.dry_run,
            )

            mode = "dry_run" if policy.dry_run else "apply"
            log_event(
                logger,
                logging.INFO,
                "retention_maintenance_completed",
                mode=mode,
                subscriptions=sub_deleted,
                users=users_deleted,
                events_raw=events_deleted,
                daily_aggregates=agg_deleted,
            )

            table_counts = await get_table_row_counts()
            for table, rows in table_counts.items():
                log_event(
                    logger,
                    logging.INFO,
                    "db_table_size",
                    table=table,
                    rows=rows,
                )
            inc_metric("background_task_success_total", task="retention_maintenance")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Ошибка в retention maintenance loop: %s", e, exc_info=True)
            inc_metric("background_task_error_total", task="retention_maintenance")
        await asyncio.sleep(24 * 3600)
