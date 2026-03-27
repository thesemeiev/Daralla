"""
Функции инициализации и мониторинга бота
"""
import logging
import datetime
import asyncio

from ..db import init_all_db
from ..services import NotificationManager

logger = logging.getLogger(__name__)

# Защита от повторной инициализации: bot.run() вызывает ensure_db_and_servers_ready до webhook,
# затем on_startup — второй вызов пропускается.
_bootstrap_completed = False


async def ensure_db_and_servers_ready():
    """
    БД + менеджер серверов из конфига. Нужно до приёма HTTP (Quart стартует в отдельном потоке раньше post_init).
    """
    global _bootstrap_completed
    if _bootstrap_completed:
        return
    await init_all_db()

    try:
        from bot.prices_config import refresh_prices_from_db
        await refresh_prices_from_db()
    except Exception as e:
        logger.warning("Не удалось подтянуть цены из БД: %s", e)

    try:
        from bot.events import EVENTS_MODULE_ENABLED
        if EVENTS_MODULE_ENABLED:
            from bot.events.db.migrations import init_events_tables
            await init_events_tables()
    except ImportError:
        pass
    except (RuntimeError, ValueError) as e:
        logger.warning("Модуль событий: не удалось инициализировать таблицы: %s", e)

    from ..bot import init_server_managers
    await init_server_managers()
    logger.info("БД и менеджер серверов готовы (до приёма HTTP-запросов)")
    _bootstrap_completed = True


async def notify_admin(bot, admin_ids, text, *, level="error"):
    """Отправляет сообщение всем администраторам.

    level: 'error' — сбой или недоступность; 'warning' — деградация; 'info' — нормальное событие (например, восстановление).
    """
    if not admin_ids:
        logger.warning("Список администраторов пуст")
        return

    headers = {
        "error": "Daralla — ошибка",
        "warning": "Daralla — внимание",
        "info": "Daralla — событие",
    }
    header = headers.get(level, headers["error"])
    full_text = f"{header}\n\n{text}"

    for admin_id in admin_ids:
        try:
            async with asyncio.timeout(10):
                await bot.send_message(
                    chat_id=admin_id,
                    text=full_text,
                    disable_web_page_preview=True,
                )
                logger.info("Успешно отправлено уведомление админу %s", admin_id)
        except (TimeoutError, RuntimeError) as e:
            logger.error("Ошибка при отправке уведомления админу %s: %s", admin_id, e)


async def notify_server_issues(bot, admin_ids, server_name, issue_type, details=""):
    """Уведомляет администраторов о состоянии ноды (панель 3X-UI)."""
    try:
        ts = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")

        if issue_type == "Сервер восстановлен":
            body = f"Сервер «{server_name}» снова отвечает на проверки.\nВремя: {ts}"
            if details:
                body += f"\n{details}"
            await notify_admin(bot, admin_ids, body, level="info")
            return

        level = "warning" if "Длительная" in issue_type else "error"
        lines = [
            f"Сервер: «{server_name}»",
            f"Событие: {issue_type}",
            f"Время: {ts}",
        ]
        if details:
            lines.append(f"Подробности: {details}")
        if level == "error":
            lines.append("")
            lines.append("Что проверить: доступность хоста и порта панели, логи 3X-UI и сеть до ноды.")
        else:
            lines.append("")
            lines.append("Сервер не проходит проверки дольше обычного — стоит посмотреть нагрузку и связность.")

        await notify_admin(bot, admin_ids, "\n".join(lines), level=level)

    except (RuntimeError, ValueError) as e:
        logger.error("Ошибка отправки уведомления о проблеме с сервером: %s", e)


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
            health_results = await server_manager.check_all_servers_health(force_check=False)
            
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
            
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Ошибка в мониторинге серверов: {e}")
        
        await asyncio.sleep(300)


async def on_startup(app):
    """Инициализация бота при запуске"""
    try:
        from ..app_context import get_ctx
        ctx = get_ctx()

        server_manager = ctx.server_manager
        subscription_manager = ctx.subscription_manager
        sync_manager = ctx.sync_manager
        admin_ids = ctx.admin_ids
        
        logger.info("=== НАЧАЛО ИНИЦИАЛИЗАЦИИ БОТА ===")

        await ensure_db_and_servers_ready()
        # После init_server_managers контекст может быть перезаписан повторной загрузкой bot.bot —
        # используем актуальный контекст с заполненным server_manager для всех дальнейших шагов
        ctx = get_ctx()
        server_manager = ctx.server_manager
        sync_manager = ctx.sync_manager
        subscription_manager = ctx.subscription_manager

        # 2. Инициализация и запуск менеджера уведомлений
        notification_manager = NotificationManager(app.bot, server_manager, admin_ids)
        await notification_manager.initialize()
        await notification_manager.start()
        ctx.notification_manager = notification_manager
        logger.info("Менеджер уведомлений запущен")
        # Устанавливаем задачу периодического бекапа БД (каждые 2 часа)
        try:
            from ..services.backup import install_backup_task
            install_backup_task(app, interval_seconds=2 * 60 * 60)
            logger.info("Backup task установлен")
        except (RuntimeError, ValueError) as e:
            logger.warning(f"Не удалось установить backup task: {e}")
        logger.info("=== ИНИЦИАЛИЗАЦИЯ БОТА ЗАВЕРШЕНА ===")
        
        # 3. Запуск фоновых задач (единый цикл)
        from .tasks import start_background_tasks
        await start_background_tasks(sync_manager, subscription_manager, notification_manager, server_manager)
        
        # 4. Запуск мониторинга здоровья серверов
        asyncio.create_task(server_health_monitor(app, server_manager, admin_ids))
        
    except (RuntimeError, ValueError, OSError) as e:
        logger.error(f"Ошибка инициализации бота: {e}")
        raise
