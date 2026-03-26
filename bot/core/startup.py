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
        from bot.events import EVENTS_MODULE_ENABLED
        if EVENTS_MODULE_ENABLED:
            from bot.events.db.migrations import init_events_tables
            await init_events_tables()
    except ImportError:
        pass
    except (RuntimeError, ValueError) as e:
        logger.warning("Модуль событий: не удалось инициализировать таблицы: %s", e)

    logger.info("БД готова (до приёма HTTP-запросов)")
    _bootstrap_completed = True


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
                    text=f"[VPNBot ERROR]\n{text}",
                    disable_web_page_preview=True
                )
                logger.info(f"Успешно отправлено уведомление админу {admin_id}")
        except (TimeoutError, RuntimeError) as e:
            logger.error(f'Ошибка при отправке уведомления админу {admin_id}: {e}')


async def on_startup(app):
    """Инициализация бота при запуске"""
    try:
        from ..app_context import get_ctx
        ctx = get_ctx()

        subscription_manager = ctx.subscription_manager
        admin_ids = ctx.admin_ids
        
        logger.info("=== НАЧАЛО ИНИЦИАЛИЗАЦИИ БОТА ===")

        await ensure_db_and_servers_ready()
        ctx = get_ctx()
        subscription_manager = ctx.subscription_manager
        if ctx.remnawave_service:
            ctx.remnawave_service.log_runtime_readiness()

        # 2. Инициализация и запуск менеджера уведомлений
        notification_manager = NotificationManager(app.bot, admin_ids)
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
        await start_background_tasks(subscription_manager, notification_manager)
        
    except (RuntimeError, ValueError, OSError) as e:
        logger.error(f"Ошибка инициализации бота: {e}")
        raise
