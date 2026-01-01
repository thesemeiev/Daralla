"""
Обработчик команды /mykey
"""
import logging
import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from ...utils import (
    UIEmojis, UIStyles, safe_edit_or_reply_universal,
    safe_edit_message_with_photo,
    check_private_chat, calculate_time_remaining
)
from ...navigation import NavigationBuilder, NavStates, CallbackData, MenuTypes
from ...db.subscribers_db import get_all_active_subscriptions_by_user, get_subscription_servers

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
        }
    except (ImportError, AttributeError):
        return {
            'nav_system': None,
            'server_manager': None,
            'subscription_manager': None,
        }


async def show_subscription_details(message, sub: dict, subscription_manager, update=None, context=None):
    """
    Показывает детали конкретной подписки.
    """
    import time
    import os
    current_time = int(time.time())
    expires_at = sub["expires_at"]
    
    # Получаем список серверов подписки
    servers = await get_subscription_servers(sub["id"])
    server_count = len(servers)
    
    # Получаем главное название VPN
    try:
        from ... import bot as bot_module
        vpn_brand_name = getattr(bot_module, 'VPN_BRAND_NAME', 'Daralla VPN')
    except (ImportError, AttributeError):
        vpn_brand_name = 'Daralla VPN'
    
    # Формируем URL подписки
    subscription_base_url = os.getenv("SUBSCRIPTION_URL", "").rstrip("/")
    webhook_url = os.getenv("WEBHOOK_URL", "").rstrip("/")
    
    # Если SUBSCRIPTION_URL не установлен, извлекаем базовый URL из WEBHOOK_URL
    # (убираем путь /webhook/yookassa, оставляем только домен)
    if subscription_base_url:
        base_url = subscription_base_url
    elif webhook_url:
        # Извлекаем базовый URL (домен) из WEBHOOK_URL
        from urllib.parse import urlparse
        parsed = urlparse(webhook_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
    else:
        base_url = None
    
    if base_url:
        subscription_url = f"{base_url}/sub/{sub['subscription_token']}"
    else:
        subscription_url = f"http://localhost:5000/sub/{sub['subscription_token']}"
        logger.warning("⚠️ WEBHOOK_URL не установлен!")
    
    # Форматируем даты
    expiry_datetime = datetime.datetime.fromtimestamp(expires_at)
    expiry_str = expiry_datetime.strftime('%d.%m.%Y %H:%M')
    created_datetime = datetime.datetime.fromtimestamp(sub['created_at'])
    created_str = created_datetime.strftime('%d.%m.%Y %H:%M')
    
    sub_name = sub.get('name', 'Подписка')
    
    # Формируем сообщение
    if expires_at > current_time:
        time_remaining = calculate_time_remaining(expires_at)
        subscription_message = (
            f"{UIStyles.header(f'Подписка: {sub_name}')}\n\n"
            f"<b>Подписка активна</b> {UIEmojis.SUCCESS}\n\n"
            f"<b>Создана:</b> {created_str}\n"
            f"<b>Истекает:</b> {expiry_str}\n"
            f"<b>Осталось:</b> {time_remaining}\n"
            f"<b>Устройств:</b> {sub['device_limit']}\n\n"
            f"{UIStyles.subheader('Ссылка на подписку:')}\n"
            f"<code>{subscription_url}</code>\n\n"
            f"{UIStyles.description('Используйте эту ссылку для импорта в VPN-клиент.')}"
        )
        
        from ...utils import UIButtons
        webapp_button = UIButtons.create_webapp_button(
            action='subscriptions',
            text="Назад к списку"
        )
        
        keyboard_buttons = [
            [InlineKeyboardButton("Продлить подписку", callback_data=f"{CallbackData.EXTEND_SUB}{sub['id']}")],
            [InlineKeyboardButton(f"{UIEmojis.EDIT} Переименовать", callback_data=f"{CallbackData.RENAME_SUB}{sub['id']}")]
        ]
        
        if webapp_button:
            keyboard_buttons.append([webapp_button])
        else:
            keyboard_buttons.append([InlineKeyboardButton(f"{UIEmojis.BACK} Назад к списку", callback_data=CallbackData.SUBSCRIPTIONS_MENU)])
    else:
        subscription_message = (
            f"{UIStyles.header(f'Подписка: {sub_name}')}\n\n"
            f"{UIEmojis.ERROR} <b>Подписка истекла</b>\n\n"
            f"<b>Создана:</b> {created_str}\n"
            f"<b>Истекла:</b> {expiry_str}\n"
            f"<b>Серверов:</b> {server_count}\n"
            f"<b>Устройств:</b> {sub['device_limit']}\n\n"
            f"{UIStyles.description('Ваша подписка истекла. Продлите её для продолжения использования.')}"
        )
        
        from ...utils import UIButtons
        webapp_button = UIButtons.create_webapp_button(
            action='subscriptions',
            text="Назад к списку"
        )
        
        keyboard_buttons = [
            [InlineKeyboardButton("Продлить подписку", callback_data=f"{CallbackData.EXTEND_SUB}{sub['id']}")]
        ]
        
        if webapp_button:
            keyboard_buttons.append([webapp_button])
        else:
            keyboard_buttons.append([InlineKeyboardButton(f"{UIEmojis.BACK} Назад к списку", callback_data=CallbackData.SUBSCRIPTIONS_MENU)])
    
    keyboard = InlineKeyboardMarkup(keyboard_buttons)
    
    # Если это callback_query, используем safe_edit_message_with_photo для правильного редактирования медиа
    if update and update.callback_query and message:
        await safe_edit_message_with_photo(
            context.bot if context else update.callback_query.message.bot,
            chat_id=message.chat.id,
            message_id=message.message_id,
            text=subscription_message,
            reply_markup=keyboard,
            parse_mode="HTML",
            menu_type=MenuTypes.SUBSCRIPTIONS_MENU
        )
    else:
        await safe_edit_or_reply_universal(
            message,
            subscription_message,
            reply_markup=keyboard,
            parse_mode="HTML",
            menu_type=MenuTypes.SUBSCRIPTIONS_MENU
        )


async def mykey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /mykey"""
    if not await check_private_chat(update):
        return
    
    globals_dict = get_globals()
    nav_system = globals_dict['nav_system']
    subscription_manager = globals_dict.get('subscription_manager')
    
    # Добавляем состояние в стек только если функция вызывается напрямую (не через навигационную систему)
    # Если функция вызывается через навигационную систему, состояние уже добавлено в стек
    # Добавляем состояние в стек только если функция вызывается напрямую (не через навигационную систему)
    # Если функция вызывается через навигационную систему, состояние уже добавлено в стек
    # НО: для пагинации не нужно вызывать navigate_to_state, так как мы остаемся в том же меню
    if update.callback_query and not context.user_data.get('_nav_called', False):
        callback_data = update.callback_query.data if update.callback_query.data else ''
        from ...utils import safe_answer_callback_query
        await safe_answer_callback_query(update.callback_query)
        # Если это пагинация, не вызываем navigate_to_state (остаемся в том же меню)
        if callback_data.startswith(CallbackData.SUBS_PAGE):
            # Продолжаем обработку пагинации без вызова navigate_to_state
            pass
        elif nav_system:
            await nav_system.navigate_to_state(update, context, NavStates.SUBSCRIPTIONS_MENU)
            return  # navigate_to_state уже вызвал эту функцию через MenuHandlers
    
    user = update.effective_user
    user_id = str(user.id)
    message = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    if message is None:
        logger.error("mykeys_menu: message is None")
        return
    
    # Шаг 1: Проверяем наличие активных подписок
    if subscription_manager:
        try:
            all_subs = await get_all_active_subscriptions_by_user(user_id)
            if all_subs:
                import time
                current_time = int(time.time())
                
                # Проверяем, есть ли callback_data для выбора конкретной подписки или пагинации
                if update.callback_query and update.callback_query.data:
                    if update.callback_query.data.startswith(CallbackData.SUBS_PAGE):
                        # Пагинация - просто продолжаем показ списка (обработается ниже)
                        pass
                    elif update.callback_query.data.startswith(CallbackData.VIEW_SUB):
                        # Показываем детали конкретной подписки
                        sub_id = int(update.callback_query.data.split(':')[1])
                        sub = next((s for s in all_subs if s['id'] == sub_id), None)
                        if sub:
                            await show_subscription_details(message, sub, subscription_manager, update, context)
                            return
                    elif update.callback_query.data.startswith(CallbackData.RENAME_SUB):
                        # Переименование подписки - сохраняем ID в контекст и запрашиваем новое имя
                        sub_id = int(update.callback_query.data.split(':')[1])
                        context.user_data['rename_subscription_id'] = sub_id
                        context.user_data['rename_subscription_message_id'] = message.message_id
                        context.user_data['rename_subscription_chat_id'] = message.chat.id
                        
                        # Проверяем, что подписка принадлежит пользователю
                        from ...db.subscribers_db import get_subscription_by_id
                        sub_check = await get_subscription_by_id(sub_id, user_id)
                        if not sub_check:
                            error_message = (
                                f"{UIStyles.header('Переименование подписки')}\n\n"
                                f"{UIEmojis.ERROR} <b>Ошибка:</b> Подписка не найдена или не принадлежит вам!\n\n"
                                f"{UIStyles.description('Попробуйте выбрать подписку из списка.')}"
                            )
                            from ...utils import UIButtons
                            webapp_back_button = UIButtons.create_webapp_button(
                                action='subscriptions',
                                text="Назад"
                            )
                            
                            if webapp_back_button:
                                keyboard = InlineKeyboardMarkup([[webapp_back_button]])
                            else:
                                keyboard = InlineKeyboardMarkup([
                                    [InlineKeyboardButton(f"{UIEmojis.BACK} Назад", callback_data=CallbackData.SUBSCRIPTIONS_MENU)]
                                ])
                            if update.callback_query:
                                await safe_edit_message_with_photo(
                                    context.bot,
                                    chat_id=message.chat.id,
                                    message_id=message.message_id,
                                    text=error_message,
                                    reply_markup=keyboard,
                                    parse_mode="HTML",
                                    menu_type=MenuTypes.SUBSCRIPTIONS_MENU
                                )
                            else:
                                await safe_edit_or_reply_universal(
                                    message,
                                    error_message,
                                    reply_markup=keyboard,
                                    parse_mode="HTML",
                                    menu_type=MenuTypes.SUBSCRIPTIONS_MENU
                                )
                            return
                        
                        rename_message = (
                            f"{UIStyles.header('Переименование подписки')}\n\n"
                            f"{UIStyles.description('Введите новое имя для подписки (максимум 50 символов):')}"
                        )
                        from ...utils import UIButtons
                        webapp_cancel_button = UIButtons.create_webapp_button(
                            action='subscriptions',
                            text="Отмена"
                        )
                        
                        if webapp_cancel_button:
                            keyboard = InlineKeyboardMarkup([[webapp_cancel_button]])
                        else:
                            keyboard = InlineKeyboardMarkup([
                                [InlineKeyboardButton(f"{UIEmojis.BACK} Отмена", callback_data=CallbackData.SUBSCRIPTIONS_MENU)]
                            ])
                        if update.callback_query:
                            await safe_edit_message_with_photo(
                                context.bot,
                                chat_id=message.chat.id,
                                message_id=message.message_id,
                                text=rename_message,
                                reply_markup=keyboard,
                                parse_mode="HTML",
                                menu_type=MenuTypes.SUBSCRIPTIONS_MENU
                            )
                        else:
                            await safe_edit_or_reply_universal(
                                message,
                                rename_message,
                                reply_markup=keyboard,
                                parse_mode="HTML",
                                menu_type=MenuTypes.SUBSCRIPTIONS_MENU
                            )
                        return
                
                # Показываем список всех подписок с пагинацией
                page_size = 5
                current_page = 0
                
                # Получаем текущую страницу из callback_data
                # Формат: subs_page_{page} (например, subs_page_0, subs_page_1)
                if update.callback_query and update.callback_query.data and update.callback_query.data.startswith(CallbackData.SUBS_PAGE):
                    try:
                        # Извлекаем номер страницы после "subs_page_"
                        page_str = update.callback_query.data.replace(CallbackData.SUBS_PAGE, '')
                        current_page = int(page_str)
                    except (ValueError, IndexError):
                        current_page = 0
                
                total_pages = (len(all_subs) + page_size - 1) // page_size
                start_idx = current_page * page_size
                end_idx = min(start_idx + page_size, len(all_subs))
                page_subs = all_subs[start_idx:end_idx]
                
                subscriptions_list = []
                keyboard_buttons = []
                
                for sub in page_subs:
                    expires_at = sub["expires_at"]
                    expiry_datetime = datetime.datetime.fromtimestamp(expires_at)
                    expiry_str = expiry_datetime.strftime('%d.%m.%Y')
                    
                    # Статус подписки
                    if expires_at > current_time:
                        status_emoji = UIEmojis.SUCCESS
                        status_text = "Активна"
                    else:
                        status_emoji = UIEmojis.ERROR
                        status_text = "Истекла"
                    
                    sub_name = sub.get('name', f"Подписка {all_subs.index(sub) + 1}")
                    subscriptions_list.append(
                        f"{status_emoji} <b>{sub_name}</b>\n"
                        f"   Окончание: {expiry_str} | {status_text}\n"
                    )
                    
                    # Кнопка для просмотра деталей подписки
                    keyboard_buttons.append([
                        InlineKeyboardButton(
                            f" {sub_name}",
                            callback_data=f"{CallbackData.VIEW_SUB}{sub['id']}"
                        )
                    ])
                
                # Кнопки пагинации
                if len(all_subs) > page_size:
                    pagination_buttons = []
                    if current_page > 0:
                        pagination_buttons.append(InlineKeyboardButton(f"{UIEmojis.ARROW_LEFT} Назад", callback_data=f"{CallbackData.SUBS_PAGE}{current_page - 1}"))
                    if current_page < total_pages - 1:
                        pagination_buttons.append(InlineKeyboardButton(f"Вперед {UIEmojis.ARROW_RIGHT}", callback_data=f"{CallbackData.SUBS_PAGE}{current_page + 1}"))
                    if pagination_buttons:
                        keyboard_buttons.append(pagination_buttons)
                
                # Добавляем кнопку покупки новой подписки
                keyboard_buttons.append([
                    InlineKeyboardButton(f"{UIEmojis.ADD} Купить новую подписку", callback_data=CallbackData.BUY_MENU)
                ])
                keyboard_buttons.append([NavigationBuilder.create_back_button()])
                
                subscriptions_text = "\n".join(subscriptions_list)
                page_info = f" (стр. {current_page + 1}/{total_pages})" if len(all_subs) > page_size else ""
                message_text = (
                    f"{UIStyles.header(f'Мои подписки{page_info}')}\n\n"
                    f"{subscriptions_text}\n"
                    f"{UIStyles.description('Выберите подписку для просмотра деталей или купите новую.')}"
                )
                
                keyboard = InlineKeyboardMarkup(keyboard_buttons)
                
                # Если это callback_query, используем safe_edit_message_with_photo для правильного редактирования медиа
                if update.callback_query:
                    await safe_edit_message_with_photo(
                        context.bot,
                        chat_id=message.chat.id,
                        message_id=message.message_id,
                        text=message_text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        menu_type=MenuTypes.SUBSCRIPTIONS_MENU
                    )
                else:
                    await safe_edit_or_reply_universal(
                        message,
                        message_text,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        menu_type=MenuTypes.SUBSCRIPTIONS_MENU
                    )
                return
        except Exception as sub_e:
            logger.error(f"Ошибка при получении подписок для user_id={user_id}: {sub_e}")
    
    # Если подписок нет, показываем сообщение
    no_subs_message = (
        f"{UIStyles.header('Ваши подписки')}\n\n"
        f"{UIEmojis.INFO} У вас пока нет активных подписок.\n\n"
        f"{UIStyles.description('Купите новую подписку, чтобы начать пользоваться VPN.')}"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Купить подписку", callback_data=CallbackData.BUY_MENU)],
        [NavigationBuilder.create_back_button()]
    ])
    # Если это callback_query, используем safe_edit_message_with_photo для правильного редактирования медиа
    if update.callback_query:
        await safe_edit_message_with_photo(
            context.bot,
            chat_id=message.chat.id,
            message_id=message.message_id,
            text=no_subs_message,
            reply_markup=keyboard,
            parse_mode="HTML",
            menu_type=MenuTypes.SUBSCRIPTIONS_MENU
        )
    else:
        await safe_edit_or_reply_universal(
            message,
            no_subs_message,
            reply_markup=keyboard,
            parse_mode="HTML",
            menu_type=MenuTypes.SUBSCRIPTIONS_MENU
        )

