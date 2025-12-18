"""
Обработчик команды /mykey
"""
import logging
import json
import datetime
import hashlib
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from ...utils import (
    UIEmojis, UIStyles, safe_edit_or_reply_universal, safe_edit_or_reply,
    check_private_chat, calculate_time_remaining
)
from ...navigation import NavigationBuilder, NavStates
from ...db.subscribers_db import get_active_subscription_by_user, get_subscription_servers

logger = logging.getLogger(__name__)

# Импортируем глобальные переменные из bot.py
def get_globals():
    """Получает глобальные переменные из bot.py"""
    try:
        from ... import bot as bot_module
        return {
            'nav_system': getattr(bot_module, 'nav_system', None),
            'server_manager': getattr(bot_module, 'server_manager', None),
            'subscription_manager': getattr(bot_module, 'subscription_manager', None),
            'extension_keys_cache': getattr(bot_module, 'extension_keys_cache', {}),
        }
    except (ImportError, AttributeError):
        return {
            'nav_system': None,
            'server_manager': None,
            'subscription_manager': None,
            'extension_keys_cache': {},
        }


async def mykey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /mykey"""
    if not await check_private_chat(update):
        return
    
    globals_dict = get_globals()
    nav_system = globals_dict['nav_system']
    server_manager = globals_dict['server_manager']
    subscription_manager = globals_dict.get('subscription_manager')
    extension_keys_cache = globals_dict['extension_keys_cache']
    
    # Добавляем состояние в стек только если функция вызывается напрямую (не через навигационную систему)
    # Если функция вызывается через навигационную систему, состояние уже добавлено в стек
    if update.callback_query and not context.user_data.get('_nav_called', False):
        from ...utils import safe_answer_callback_query
        await safe_answer_callback_query(update.callback_query)
        if nav_system:
            await nav_system.navigate_to_state(update, context, NavStates.MYKEYS_MENU)
            return  # navigate_to_state уже вызвал эту функцию через MenuHandlers
    
    user = update.effective_user
    user_id = str(user.id)
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if message is None:
        logger.error("mykeys_menu: message is None")
        return
    
    # Шаг 1: Проверяем наличие активной подписки
    if subscription_manager:
        try:
            sub = await get_active_subscription_by_user(user_id)
            if sub:
                # Проверяем срок действия
                import time
                current_time = int(time.time())
                expires_at = sub["expires_at"]
                
                # Получаем список серверов подписки
                servers = await get_subscription_servers(sub["id"])
                server_count = len(servers)
                
                # Формируем URL подписки
                # WEBHOOK_URL должен быть публичным URL вашего webhook сервера
                import os
                webhook_url = os.getenv("WEBHOOK_URL", "").rstrip("/")
                
                # Формируем subscription URL
                if webhook_url:
                    subscription_url = f"{webhook_url}/sub/{sub['subscription_token']}"
                else:
                    # Если WEBHOOK_URL не установлен, используем временный fallback
                    subscription_url = f"http://localhost:5000/sub/{sub['subscription_token']}"
                    logger.warning(
                        "⚠️ WEBHOOK_URL не установлен! "
                        "Установите переменную окружения WEBHOOK_URL с публичным URL вашего webhook сервера."
                    )
                
                # Форматируем дату окончания
                expiry_datetime = datetime.datetime.fromtimestamp(expires_at)
                expiry_str = expiry_datetime.strftime('%d.%m.%Y %H:%M')
                
                # Определяем период
                period_text = "3 месяца" if sub["period"] == "3month" else "1 месяц"
                
                # Формируем сообщение о подписке
                if expires_at > current_time:
                    # Подписка активна
                    time_remaining = calculate_time_remaining(expires_at)
                    subscription_message = (
                        f"{UIStyles.header('Моя подписка')}\n\n"
                        f"{UIEmojis.SUCCESS} <b>Подписка активна</b>\n\n"
                        f"<b>Период:</b> {period_text}\n"
                        f"<b>Окончание:</b> {expiry_str}\n"
                        f"<b>Осталось:</b> {time_remaining}\n"
                        f"<b>Серверов:</b> {server_count}\n"
                        f"<b>Устройств:</b> {sub['device_limit']}\n\n"
                        f"{UIStyles.subheader('Ссылка на подписку:')}\n"
                        f"<code>{subscription_url}</code>\n\n"
                        f"{UIStyles.description('Используйте эту ссылку для импорта в VPN-клиент. Подписка включает все доступные серверы.')}"
                    )
                    
                    # Кнопки для активной подписки
                    keyboard_buttons = [
                        [InlineKeyboardButton("Продлить подписку", callback_data=f"extend_sub:{sub['id']}")],
                        [NavigationBuilder.create_back_button()]
                    ]
                else:
                    # Подписка истекла
                    subscription_message = (
                        f"{UIStyles.header('Моя подписка')}\n\n"
                        f"{UIEmojis.ERROR} <b>Подписка истекла</b>\n\n"
                        f"<b>Период:</b> {period_text}\n"
                        f"<b>Окончание:</b> {expiry_str}\n"
                        f"<b>Серверов:</b> {server_count}\n"
                        f"<b>Устройств:</b> {sub['device_limit']}\n\n"
                        f"{UIStyles.description('Ваша подписка истекла. Продлите её для продолжения использования.')}"
                    )
                    
                    # Кнопки для истекшей подписки
                    keyboard_buttons = [
                        [InlineKeyboardButton("Продлить подписку", callback_data=f"extend_sub:{sub['id']}")],
                        [InlineKeyboardButton("Купить новую подписку", callback_data="buy_menu")],
                        [NavigationBuilder.create_back_button()]
                    ]
                
                keyboard = InlineKeyboardMarkup(keyboard_buttons)
                
                await safe_edit_or_reply_universal(
                    message,
                    subscription_message,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    menu_type='mykeys_menu'
                )
                return
        except Exception as sub_e:
            logger.error(f"Ошибка при получении подписки для user_id={user_id}: {sub_e}")
            # Продолжаем показ старых ключей как fallback
    
    # Шаг 2: Если подписки нет, показываем старые ключи (legacy)
    if not server_manager:
        logger.error("server_manager не инициализирован")
        keyboard = InlineKeyboardMarkup([
            [NavigationBuilder.create_back_button()]
        ])
        await safe_edit_or_reply_universal(message, 'Ошибка: серверы не настроены.', reply_markup=keyboard, menu_type='mykeys_menu')
        return
    
    # Получаем текущую страницу из callback_data или устанавливаем 0
    current_page = 0
    if update.callback_query and update.callback_query.data.startswith('keys_page_'):
        try:
            current_page = int(update.callback_query.data.split('_')[2])
            logger.info(f"Переход на страницу {current_page} для user_id={user_id}")
        except (ValueError, IndexError):
            current_page = 0
            logger.error(f"Ошибка парсинга номера страницы: {update.callback_query.data}")
    
    try:
        # Сначала проверяем доступность серверов через кэш (1 проверка на сервер)
        # Это позволяет избежать множественных попыток подключения
        server_health_cache = {}
        for server in server_manager.servers:
            server_name = server["name"]
            # Используем кэшированную проверку здоровья (быстро, без retry)
            is_healthy = server_manager.check_server_health(server_name, force_check=False)
            server_health_cache[server_name] = is_healthy
        
        # Ищем клиентов на всех серверах
        all_clients = []
        unique_clients = {}  # Словарь для хранения уникальных клиентов по email
        unavailable_servers = []  # Список недоступных серверов
        
        for server in server_manager.servers:
            server_name = server["name"]
            
            # Пропускаем сервер, если он недоступен (проверено через кэш)
            if not server_health_cache.get(server_name, False):
                logger.debug(f"Сервер {server_name} недоступен (из кэша), пропускаем")
                unavailable_servers.append(server_name)
                continue
            
            try:
                xui = server["x3"]
                if xui is None:
                    logger.warning(f"Сервер {server_name} недоступен, пропускаем")
                    unavailable_servers.append(server_name)
                    continue
                
                # Используем list_quick() для получения списка (1 попытка, без retry)
                # Доступность сервера уже проверена через кэш выше
                inbounds = xui.list_quick()['obj']
                for inbound in inbounds:
                    settings = json.loads(inbound['settings'])
                    clients = settings.get("clients", [])
                    for client in clients:
                        if client['email'].startswith(user_id) or client['email'].startswith(f'trial_{user_id}'):
                            client['server_name'] = server['name']  # Добавляем имя сервера
                            if client['email'] not in unique_clients:
                                unique_clients[client['email']] = client
                                all_clients.append(client)
            except Exception as e:
                logger.error(f"Ошибка при получении клиентов с сервера {server['name']}: {e}")
                unavailable_servers.append(server['name'])

        # Если все серверы недоступны, уведомляем пользователя
        if unavailable_servers and len(unavailable_servers) == len(server_manager.servers):
            error_message = (
                f"{UIStyles.header('Ошибка доступа')}\n\n"
                f"{UIEmojis.ERROR} <b>Все серверы временно недоступны!</b>\n\n"
                f"{UIStyles.description('Не удалось получить список ваших ключей. Попробуйте позже.')}"
            )
            keyboard = InlineKeyboardMarkup([
                [NavigationBuilder.create_back_button()]
            ])
            await safe_edit_or_reply_universal(message, error_message, reply_markup=keyboard, parse_mode="HTML", menu_type='mykeys_menu')
            return
        
        if not all_clients:
            # Если есть недоступные серверы, но не все, сообщаем об этом
            if unavailable_servers:
                error_message = (
                    f"{UIStyles.header('Ваши ключи')}\n\n"
                    f"{UIEmojis.WARNING} <b>Некоторые серверы недоступны</b>\n\n"
                    f"Не удалось проверить ключи на серверах: {', '.join(unavailable_servers)}\n\n"
                    f"{UIStyles.description('У вас нет активных ключей на доступных серверах.')}"
                )
            else:
                error_message = 'У вас нет активных ключей.'
            
            keyboard = InlineKeyboardMarkup([
                [NavigationBuilder.create_back_button()]
            ])
            await safe_edit_or_reply_universal(message, error_message, reply_markup=keyboard, parse_mode="HTML" if unavailable_servers else None, menu_type='mykeys_menu')
            return

        # Настройки пагинации
        keys_per_page = 1  # Показываем по 1 ключу на страницу
        total_pages = (len(all_clients) + keys_per_page - 1) // keys_per_page
        
        # Ограничиваем текущую страницу
        current_page = max(0, min(current_page, total_pages - 1))
        
        # Получаем ключи для текущей страницы
        start_idx = current_page * keys_per_page
        end_idx = start_idx + keys_per_page
        page_clients = all_clients[start_idx:end_idx]
        
        # Формируем сообщение для текущей страницы
        now = int(datetime.datetime.now().timestamp())
        page_text = f"{UIStyles.header(f'Ваши ключи (стр. {current_page + 1}/{total_pages})')}\n\n"
        
        for i, client in enumerate(page_clients, start_idx + 1):
            expiry = int(client.get('expiryTime', 0) / 1000)
            is_active = client.get('enable', False) and expiry > now
            expiry_str = datetime.datetime.fromtimestamp(expiry).strftime('%d.%m.%Y %H:%M') if expiry else '—'
            status = 'Активен' if is_active else 'Неактивен'
            server_name = client.get('server_name', 'Неизвестный сервер')
            
            xui = None
            server_display_name = server_name  # По умолчанию используем server_name
            for server in server_manager.servers:
                if server['name'] == server_name:
                    xui = server['x3']
                    # Получаем display_name сервера из конфигурации
                    server_config = server.get('config', {})
                    server_display_name = server_config.get('display_name', server_name)
                    break
            
            if xui:
                try:
                    # Передаем display_name сервера для tag в ссылке (только название сервера, без главного названия)
                    link = xui.link(client["email"], server_name=server_display_name)
                except Exception as link_e:
                    logger.error(f"Ошибка получения ссылки на ключ {client['email']}: {link_e}")
                    link = "Ошибка получения ссылки"
                
                # Добавляем информацию о ключе
                status_icon = UIEmojis.SUCCESS if status == "Активен" else UIEmojis.ERROR
                
                # Вычисляем оставшееся время
                time_remaining = calculate_time_remaining(expiry)
                
                # Получаем имя ключа из поля subId
                key_name = client.get('subId', '').strip()
                if key_name:
                    page_text += f"{UIStyles.subheader(f'{i}. {key_name}')}\n"
                else:
                    page_text += f"{UIStyles.subheader(f'{i}. Ключ #{i}')}\n"
                
                page_text += f"<b>Email:</b> <code>{client['email']}</code>\n"
                page_text += f"<b>Статус:</b> {status_icon} {status}\n"
                page_text += f"<b>Сервер:</b> {server_name}\n"
                page_text += f"<b>Осталось:</b> {time_remaining}\n\n"
                page_text += f"<code>{link}</code>\n\n"
                page_text += f"{UIStyles.description('Нажмите на ключ выше, чтобы скопировать')}\n\n"
        
        # Создаем клавиатуру с навигацией
        keyboard_buttons = []
        
        # Кнопка "Продлить" для текущего ключа (если ключ не истек)
        current_client = page_clients[0] if page_clients else None
        if current_client:
            expiry = int(current_client.get('expiryTime', 0) / 1000)
            now = int(datetime.datetime.now().timestamp())
            # Показываем кнопку продления если ключ активен или истек менее чем 30 дней назад
            if expiry > now - (30 * 24 * 3600):  # Можно продлить в течение 30 дней после истечения
                # Создаем короткий идентификатор для ключа
                short_id = hashlib.md5(f"{user_id}:{current_client['email']}".encode()).hexdigest()[:8]
                extension_keys_cache[short_id] = {
                    'email': current_client['email'],
                    'created_at': datetime.datetime.now().timestamp()
                }
                keyboard_buttons.append([InlineKeyboardButton("Продлить ключ", callback_data=f"ext_key:{short_id}")])
            
        
        # Кнопки навигации по страницам
        nav_buttons = []
        if current_page > 0:
            nav_buttons.append(InlineKeyboardButton(f"Пред. {UIEmojis.PREV}", callback_data=f"keys_page_{current_page - 1}"))
        if current_page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton(f"След. {UIEmojis.NEXT}", callback_data=f"keys_page_{current_page + 1}"))
        
        if nav_buttons:
            keyboard_buttons.append(nav_buttons)
        
        # Кнопка "Назад"
        keyboard_buttons.append([NavigationBuilder.create_back_button()])
        
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        # Отправляем сообщение с пагинацией
        await safe_edit_or_reply_universal(message, page_text, reply_markup=keyboard, parse_mode="HTML", menu_type='mykeys_menu')
        
    except Exception as e:
        logger.exception(f"Ошибка в mykey для user_id={user_id}: {e}")
        keyboard = InlineKeyboardMarkup([
            [NavigationBuilder.create_back_button()]
        ])
        await safe_edit_or_reply(message, f'{UIEmojis.ERROR} Ошибка: {e}', reply_markup=keyboard)

