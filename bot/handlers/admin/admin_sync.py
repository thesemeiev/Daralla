"""
Админ-команда для ручной синхронизации БД с X-UI серверами
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes

from ...utils import UIStyles, UIEmojis
from ...navigation import NavigationBuilder

logger = logging.getLogger(__name__)


def get_globals():
    """Получает глобальные переменные из bot.py"""
    try:
        from ... import bot as bot_module
        return {
            'ADMIN_IDS': getattr(bot_module, 'ADMIN_IDS', []),
            'sync_manager': getattr(bot_module, 'sync_manager', None),
        }
    except (ImportError, AttributeError):
        return {
            'ADMIN_IDS': [],
            'sync_manager': None,
        }


async def admin_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ-команда для ручной синхронизации БД с X-UI"""
    user = update.effective_user
    user_id_int = user.id
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    sync_manager = globals_dict['sync_manager']
    
    # Проверяем доступ
    if user_id_int not in ADMIN_IDS:
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return
    
    if not sync_manager:
        await update.message.reply_text("SyncManager не доступен.")
        return
    
    # Проверяем, есть ли флаг --fix для автоматического восстановления
    auto_fix = False
    if context.args and len(context.args) > 0:
        if context.args[0] == '--fix' or context.args[0] == '--auto-fix':
            auto_fix = True
    
    # Запускаем синхронизацию
    if auto_fix:
        await update.message.reply_text("Запуск синхронизации с автоматическим восстановлением...")
    else:
        await update.message.reply_text("Запуск синхронизации БД с X-UI серверами...")
    
    try:
        # Синхронизируем все подписки
        # Для ручной команды используем auto_fix если указан флаг
        stats = await sync_manager.sync_all_subscriptions(auto_fix=auto_fix)
        
        # Формируем отчет
        report = (
            f"{UIStyles.header('Результаты синхронизации')}\n\n"
            f"{UIEmojis.SUCCESS} <b>Синхронизация завершена</b>\n\n"
            f"<b>Проверено подписок:</b> {stats['subscriptions_checked']}\n"
            f"<b>Синхронизировано:</b> {stats['subscriptions_synced']}\n"
            f"<b>Проверено серверов:</b> {stats['total_servers_checked']}\n"
            f"<b>Синхронизировано серверов:</b> {stats['total_servers_synced']}\n"
        )
        
        if stats.get('total_clients_created', 0) > 0:
            report += f"\n<b>Восстановлено клиентов:</b> {stats['total_clients_created']}\n"
        
        report += f"<b>Ошибок:</b> {stats['total_errors']}\n"
        
        if stats['errors']:
            report += f"\n{UIEmojis.WARNING} <b>Ошибки:</b>\n"
            for error in stats['errors'][:10]:  # Показываем первые 10 ошибок
                report += f"• {error}\n"
            if len(stats['errors']) > 10:
                report += f"\n... и еще {len(stats['errors']) - 10} ошибок"
        
        # Ищем orphaned клиентов
        try:
            orphaned = await sync_manager.find_orphaned_clients()
            if orphaned:
                report += f"\n\n{UIEmojis.WARNING} <b>Найдено orphaned клиентов:</b> {len(orphaned)}\n"
                report += "<i>Клиенты на серверах без записи в БД подписок</i>\n"
                report += f"\n<i>Используйте /admin_sync --fix для автоматического восстановления отсутствующих клиентов</i>"
        except Exception as e:
            logger.error(f"Ошибка поиска orphaned клиентов: {e}")
        
        keyboard = NavigationBuilder.create_main_menu_button()
        await update.message.reply_text(
            report,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        logger.info(f"Админ {user_id_int} выполнил ручную синхронизацию")
        
    except Exception as e:
        logger.error(f"Ошибка синхронизации: {e}")
        await update.message.reply_text(f"Ошибка синхронизации: {e}")

