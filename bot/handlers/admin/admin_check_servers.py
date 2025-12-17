"""
Обработчик команды /admin_check_servers
"""
import logging
import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from ...utils import (
    UIEmojis, safe_edit_or_reply_universal, safe_edit_or_reply, check_private_chat
)
from ...navigation import NavStates, CallbackData, NavigationBuilder

logger = logging.getLogger(__name__)

# Импортируем глобальные переменные из bot.py
def get_globals():
    """Получает глобальные переменные из bot.py"""
    try:
        from ... import bot as bot_module
        return {
            'ADMIN_IDS': getattr(bot_module, 'ADMIN_IDS', []),
            'server_manager': getattr(bot_module, 'server_manager', None),
            'nav_system': getattr(bot_module, 'nav_system', None),
        }
    except (ImportError, AttributeError):
        return {
            'ADMIN_IDS': [],
            'server_manager': None,
            'nav_system': None,
        }


async def admin_check_servers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Детальная проверка серверов"""
    if not await check_private_chat(update):
        return
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    server_manager = globals_dict['server_manager']
    nav_system = globals_dict['nav_system']
    
    # Добавляем состояние в стек только если функция вызывается напрямую (не через навигационную систему)
    # Если функция вызывается через навигационную систему, состояние уже добавлено в стек
    if update.callback_query and not context.user_data.get('_nav_called', False):
        from ...utils import safe_answer_callback_query
        await safe_answer_callback_query(update.callback_query)
        if nav_system:
            await nav_system.navigate_to_state(update, context, NavStates.ADMIN_CHECK_SERVERS)
            return  # navigate_to_state уже вызвал эту функцию через MenuHandlers
    
    if update.effective_user.id not in ADMIN_IDS:
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply_universal(message_obj, 'Нет доступа.', menu_type='admin_check_servers')
        return
    
    if not server_manager:
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply_universal(message_obj, 'Ошибка: серверы не настроены.', menu_type='admin_check_servers')
        return
    
    try:
        # Проверяем здоровье всех серверов (принудительная проверка для админа)
        health_results = server_manager.check_all_servers_health(force_check=True)
        health_status = server_manager.get_server_health_status()
        
        message = "🔍 Детальная проверка серверов:\n\n"
        
        for server in server_manager.servers:
            server_name = server["name"]
            is_healthy = health_results.get(server_name, False)
            status_info = health_status.get(server_name, {})
            
            if is_healthy:
                # Получаем дополнительную информацию о сервере
                try:
                    xui = server["x3"]
                    if xui is None:
                        message += f"{UIEmojis.ERROR} {server_name}: Недоступен\n"
                        continue
                    try:
                        total_clients, active_clients, expired_clients = xui.get_clients_status_count()
                    except Exception as count_e:
                        logger.error(f"Ошибка получения количества клиентов с сервера {server_name}: {count_e}")
                        message += f"{UIEmojis.ERROR} {server_name}: Ошибка получения данных\n"
                        continue
                    message += f"{UIEmojis.SUCCESS} {server_name}: Онлайн\n"
                    message += f"   Всего клиентов: {total_clients}\n"
                    message += f"   Активных клиентов: {active_clients}\n"
                    message += f"   Истекших клиентов: {expired_clients}\n"
                    message += f"   Последняя проверка: {status_info.get('last_check', 'Неизвестно')}\n"
                except Exception as e:
                    message += f"{UIEmojis.SUCCESS} {server_name}: Онлайн (ошибка получения деталей: {str(e)[:50]}...)\n"
            else:
                message += f"{UIEmojis.ERROR} {server_name}: Офлайн\n"
                message += f"   Ошибка: {status_info.get('last_error', 'Неизвестно')}\n"
                message += f"   {UIEmojis.REFRESH} Неудачных попыток: {status_info.get('consecutive_failures', 0)}\n"
                message += f"   Последняя проверка: {status_info.get('last_check', 'Неизвестно')}\n"
            
            message += "\n"
        
        # Добавляем общую статистику
        total_servers = len(server_manager.servers)
        online_servers = sum(1 for is_healthy in health_results.values() if is_healthy)
        offline_servers = total_servers - online_servers
        
        # Подсчитываем общее количество клиентов
        total_clients_all = 0
        active_clients_all = 0
        expired_clients_all = 0
        
        for server in server_manager.servers:
            if health_results.get(server["name"], False):
                try:
                    xui = server["x3"]
                    if xui is None:
                        continue
                    try:
                        total_clients, active_clients, expired_clients = xui.get_clients_status_count()
                    except Exception as count_e:
                        logger.error(f"Ошибка получения количества клиентов с сервера {server_name}: {count_e}")
                        continue
                    total_clients_all += total_clients
                    active_clients_all += active_clients
                    expired_clients_all += expired_clients
                except:
                    pass
        
        message += f"Общая статистика:\n"
        message += f"   Всего серверов: {total_servers}\n"
        message += f"   Онлайн: {online_servers}\n"
        message += f"   Офлайн: {offline_servers}\n"
        if total_servers > 0:
            message += f"   Доступность: {(online_servers/total_servers*100):.1f}%\n\n"
        else:
            message += f"   Доступность: Нет серверов\n\n"
        
        # Добавляем предупреждение, если нет доступных серверов
        if online_servers == 0:
            message += f"{UIEmojis.WARNING} <b>Внимание: Нет доступных серверов!</b>\n"
            message += f"Бот продолжит работу, но создание новых ключей будет недоступно до восстановления серверов.\n\n"
        message += f"Клиенты:\n"
        message += f"   Всего клиентов: {total_clients_all}\n"
        message += f"   Активных: {active_clients_all}\n"
        message += f"   Истекших: {expired_clients_all}\n\n"
        message += f"Время проверки: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{UIEmojis.REFRESH} Обновить", callback_data=CallbackData.ADMIN_CHECK_SERVERS)],
            [NavigationBuilder.create_back_button()]
        ])
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply_universal(message_obj, message, reply_markup=keyboard, parse_mode="HTML", menu_type='admin_check_servers')
    except Exception as e:
        logger.exception("Ошибка в admin_check_servers")
        keyboard = InlineKeyboardMarkup([
            [NavigationBuilder.create_back_button()]
        ])
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply_universal(message_obj, f'Ошибка при проверке серверов: {e}', reply_markup=keyboard, menu_type='admin_check_servers')


async def force_check_servers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принудительная проверка всех серверов"""
    if not await check_private_chat(update):
        return
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    server_manager = globals_dict['server_manager']
    
    if update.effective_user.id not in ADMIN_IDS:
        await safe_edit_or_reply(update.message, 'Нет доступа.')
        return
    
    try:
        await safe_edit_or_reply(update.message, '🔄 Принудительная проверка серверов...')
        
        # Получаем new_client_manager из глобальных переменных
        try:
            import sys
            import importlib
            if 'bot.bot' in sys.modules:
                bot_module = sys.modules['bot.bot']
            else:
                bot_module = importlib.import_module('bot.bot')
            new_client_manager = getattr(bot_module, 'new_client_manager', None)
        except (ImportError, AttributeError):
            new_client_manager = None
        
        # Проверяем все серверы (принудительная проверка для админа)
        health_results = server_manager.check_all_servers_health(force_check=True)
        new_client_health = new_client_manager.check_all_servers_health(force_check=True) if new_client_manager else {}
        
        # Формируем отчет
        message = "🔍 Результаты принудительной проверки:\n\n"
        
        # Основные серверы
        message += "Основные серверы:\n"
        total_clients_main = 0
        active_clients_main = 0
        expired_clients_main = 0
        
        for server in server_manager.servers:
            server_name = server["name"]
            is_healthy = health_results.get(server_name, False)
            status_icon = UIEmojis.SUCCESS if is_healthy else UIEmojis.ERROR
            
            if is_healthy:
                try:
                    xui = server["x3"]
                    if xui is None:
                        message += f"{status_icon} {server_name} (недоступен)\n"
                        continue
                    try:
                        total_clients, active_clients, expired_clients = xui.get_clients_status_count()
                        total_clients_main += total_clients
                        active_clients_main += active_clients
                        expired_clients_main += expired_clients
                        message += f"{status_icon} {server_name} ({total_clients}, {active_clients}, {expired_clients})\n"
                    except Exception as count_e:
                        logger.error(f"Ошибка получения количества клиентов с сервера {server_name}: {count_e}")
                        message += f"{status_icon} {server_name} (ошибка получения данных)\n"
                except Exception as e:
                    logger.error(f"Ошибка обработки сервера {server_name}: {e}")
                    message += f"{status_icon} {server_name} (ошибка)\n"
            else:
                message += f"{status_icon} {server_name}\n"
        
        message += "\nСерверы для новых клиентов:\n"
        total_clients_new = 0
        active_clients_new = 0
        expired_clients_new = 0
        
        if new_client_manager:
            for server in new_client_manager.servers:
                server_name = server["name"]
                is_healthy = new_client_health.get(server_name, False)
                status_icon = UIEmojis.SUCCESS if is_healthy else UIEmojis.ERROR
                
                if is_healthy:
                    try:
                        xui = server["x3"]
                        if xui is None:
                            message += f"{status_icon} {server_name} (недоступен)\n"
                            continue
                        try:
                            total_clients, active_clients, expired_clients = xui.get_clients_status_count()
                        except Exception as count_e:
                            logger.error(f"Ошибка получения количества клиентов с сервера {server_name}: {count_e}")
                            message += f"{status_icon} {server_name} (ошибка получения данных)\n"
                            continue
                        total_clients_new += total_clients
                        active_clients_new += active_clients
                        expired_clients_new += expired_clients
                        message += f"{status_icon} {server_name} ({total_clients}, {active_clients}, {expired_clients})\n"
                    except:
                        message += f"{status_icon} {server_name} (ошибка получения данных)\n"
                else:
                    message += f"{status_icon} {server_name}\n"
        
        # Статистика
        total_servers = len(health_results) + len(new_client_health)
        online_servers = sum(1 for is_healthy in list(health_results.values()) + list(new_client_health.values()) if is_healthy)
        total_clients_all = total_clients_main + total_clients_new
        active_clients_all = active_clients_main + active_clients_new
        expired_clients_all = expired_clients_main + expired_clients_new
        
        message += f"\nСтатистика серверов:\n"
        message += f"Всего серверов: {total_servers}\n"
        message += f"Онлайн: {online_servers}\n"
        message += f"Офлайн: {total_servers - online_servers}\n"
        message += f"Доступность: {(online_servers/total_servers*100):.1f}%\n\n"
        message += f"Статистика клиентов:\n"
        message += f"Всего клиентов: {total_clients_all}\n"
        message += f"Активных: {active_clients_all}\n"
        message += f"Истекших: {expired_clients_all}\n\n"
        message += f"Время проверки: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        
        await safe_edit_or_reply(update.message, message, parse_mode="HTML")
        
    except Exception as e:
        logger.exception("Ошибка в force_check_servers")
        await safe_edit_or_reply(update.message, f'Ошибка при проверке серверов: {e}')

