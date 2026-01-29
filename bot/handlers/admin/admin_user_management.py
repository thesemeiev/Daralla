"""
Админ-панель для управления пользователями и подписками
"""
import logging
import datetime
import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from ...utils import UIEmojis, UIStyles, safe_edit_or_reply_universal, check_private_chat
from ...navigation import NavStates, CallbackData, MenuTypes, NavigationBuilder
from telegram.ext import ConversationHandler, MessageHandler, filters
from ...db import (
    get_user_by_id, get_all_subscriptions_by_user, get_payments_by_user,
    get_subscription_servers, update_subscription_status,
    update_subscription_expiry, get_subscription_by_token,
    resolve_user_by_query,
)

logger = logging.getLogger(__name__)

# Константа для состояния поиска пользователя
SEARCH_USER_WAITING_ID = 2001

def get_globals():
    """Получает глобальные переменные из bot.py"""
    try:
        from ... import bot as bot_module
        return {
            'ADMIN_IDS': getattr(bot_module, 'ADMIN_IDS', []),
            'subscription_manager': getattr(bot_module, 'subscription_manager', None),
            'server_manager': getattr(bot_module, 'server_manager', None),
            'nav_system': getattr(bot_module, 'nav_system', None),
        }
    except (ImportError, AttributeError):
        return {
            'ADMIN_IDS': [],
            'subscription_manager': None,
            'server_manager': None,
            'nav_system': None,
        }


async def admin_search_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Поиск пользователя - показывает инструкцию"""
    if not await check_private_chat(update):
        return ConversationHandler.END
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    # Если это callback_query, отвечаем на него
    if update.callback_query:
        from ...utils import safe_answer_callback_query
        await safe_answer_callback_query(update.callback_query)
    
    if update.effective_user.id not in ADMIN_IDS:
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply_universal(message_obj, 'Нет доступа.', menu_type=MenuTypes.ADMIN_MENU)
        return ConversationHandler.END
    
    # Очищаем старые данные поиска при новом запуске
    context.user_data.pop('admin_search_menu_message_id', None)
    context.user_data.pop('admin_search_menu_chat_id', None)
    context.user_data.pop('admin_search_timestamp', None)
    
    # Если передан идентификатор как аргумент команды
    if update.message and context.args and len(context.args) > 0:
        query = context.args[0]
        user = await resolve_user_by_query(query)
        if user:
            await show_user_info(update, context, user["user_id"])
        else:
            message_obj = update.message
            await safe_edit_or_reply_universal(
                message_obj,
                f"{UIEmojis.ERROR} Пользователь не найден по запросу <code>{query}</code>.",
                parse_mode="HTML", menu_type=MenuTypes.ADMIN_SEARCH_USER
            )
        return ConversationHandler.END
    
    message = (
        f"{UIStyles.header('Поиск пользователя')}\n\n"
        f"{UIStyles.description('Введите Telegram ID, ID аккаунта (tg_… / web_…) или логин:')}\n\n"
        f"{UIStyles.description('Примеры: 123456789, web_ivan, ivan')}"
    )
    
    keyboard = InlineKeyboardMarkup([
        [NavigationBuilder.create_back_button()]
    ])
    
    message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
    result = await safe_edit_or_reply_universal(message_obj, message, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_SEARCH_USER)
    
    # Сохраняем message_id меню поиска для дальнейшего редактирования
    if message_obj:
        context.user_data['admin_search_menu_message_id'] = message_obj.message_id
        context.user_data['admin_search_menu_chat_id'] = message_obj.chat.id
        # Сохраняем timestamp для проверки "застрявших" состояний
        import time
        context.user_data['admin_search_timestamp'] = time.time()
    
    return SEARCH_USER_WAITING_ID


async def admin_search_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ввод user_id для поиска пользователя"""
    if not await check_private_chat(update):
        # Очищаем состояние при выходе
        context.user_data.pop('admin_search_menu_message_id', None)
        context.user_data.pop('admin_search_menu_chat_id', None)
        return ConversationHandler.END
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    if update.effective_user.id not in ADMIN_IDS:
        # Очищаем состояние при отсутствии доступа
        context.user_data.pop('admin_search_menu_message_id', None)
        context.user_data.pop('admin_search_menu_chat_id', None)
        return ConversationHandler.END
    
    try:
        query = update.message.text.strip()
        user = await resolve_user_by_query(query)
        if not user:
            from ...utils import safe_edit_or_reply_universal
            from ...navigation import NavigationBuilder, MenuTypes
            error_message = (
                f"{UIStyles.header('Поиск пользователя')}\n\n"
                f"{UIEmojis.ERROR} <b>Пользователь не найден</b>\n\n"
                f"{UIStyles.description('Введите Telegram ID, ID аккаунта (tg_… / web_…) или логин')}"
            )
            keyboard = InlineKeyboardMarkup([
                [NavigationBuilder.create_back_button()]
            ])
            menu_message_id = context.user_data.get('admin_search_menu_message_id')
            menu_chat_id = context.user_data.get('admin_search_menu_chat_id')
            if menu_chat_id and menu_message_id:
                from ...utils import safe_edit_message_with_photo
                await safe_edit_message_with_photo(
                    context.bot, menu_chat_id, menu_message_id, error_message, 
                    reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_SEARCH_USER
                )
            else:
                await safe_edit_or_reply_universal(
                    update.message, error_message, reply_markup=keyboard, 
                    parse_mode="HTML", menu_type=MenuTypes.ADMIN_SEARCH_USER
                )
            # НЕ очищаем состояние, чтобы пользователь мог попробовать снова
            return SEARCH_USER_WAITING_ID
        
        # Удаляем сообщение пользователя с ID
        try:
            await update.message.delete()
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение пользователя: {e}")
        
        # Получаем message_id меню поиска из context
        menu_message_id = context.user_data.get('admin_search_menu_message_id')
        menu_chat_id = context.user_data.get('admin_search_menu_chat_id')
        
        user_id = user["user_id"]
        # Передаем информацию о сообщении для редактирования
        await show_user_info(update, context, user_id, menu_chat_id=menu_chat_id, menu_message_id=menu_message_id)
        
    except Exception as e:
        logger.error(f"Ошибка в admin_search_user_input: {e}", exc_info=True)
        from ...utils import safe_edit_or_reply_universal
        from ...navigation import NavigationBuilder, MenuTypes
        error_message = (
            f"{UIStyles.header('Поиск пользователя')}\n\n"
            f"{UIEmojis.ERROR} <b>Ошибка:</b> {str(e)}\n\n"
            f"{UIStyles.description('Попробуйте еще раз или вернитесь назад.')}"
        )
        keyboard = InlineKeyboardMarkup([
            [NavigationBuilder.create_back_button()]
        ])
        menu_message_id = context.user_data.get('admin_search_menu_message_id')
        menu_chat_id = context.user_data.get('admin_search_menu_chat_id')
        if menu_chat_id and menu_message_id:
            from ...utils import safe_edit_message_with_photo
            await safe_edit_message_with_photo(
                context.bot, menu_chat_id, menu_message_id, error_message, 
                reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_SEARCH_USER
            )
        else:
            await safe_edit_or_reply_universal(
                update.message, error_message, reply_markup=keyboard, 
                parse_mode="HTML", menu_type=MenuTypes.ADMIN_SEARCH_USER
            )
    finally:
        # ВСЕГДА очищаем данные поиска из context после завершения
        context.user_data.pop('admin_search_menu_message_id', None)
        context.user_data.pop('admin_search_menu_chat_id', None)
        context.user_data.pop('admin_search_timestamp', None)
    
    return ConversationHandler.END


async def show_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str, menu_chat_id=None, menu_message_id=None):
    """Показывает информацию о пользователе"""
    try:
        # Получаем информацию о пользователе
        user = await get_user_by_id(user_id)
        if not user:
            message = (
                f"{UIEmojis.ERROR} <b>Пользователь не найден</b>\n\n"
                f"Пользователь с ID <code>{user_id}</code> не найден в базе данных."
            )
            keyboard = InlineKeyboardMarkup([
                [NavigationBuilder.create_back_button()]
            ])
            # Используем menu_chat_id и menu_message_id для редактирования, если они есть
            if menu_chat_id and menu_message_id:
                # Теперь у всех меню есть фото, используем safe_edit_message_with_photo
                from ...utils.message_helpers import safe_edit_message_with_photo
                bot = update.message.get_bot() if update.message else (update.callback_query.message.get_bot() if update.callback_query else None)
                if bot:
                    try:
                        await safe_edit_message_with_photo(bot, menu_chat_id, menu_message_id, message, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_SEARCH_USER)
                    except Exception as e:
                        logger.error(f"Не удалось отредактировать сообщение через safe_edit_message_with_photo: {e}")
                        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
                        await safe_edit_or_reply_universal(message_obj, message, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_SEARCH_USER)
                else:
                    message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
                    await safe_edit_or_reply_universal(message_obj, message, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_SEARCH_USER)
            else:
                message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
                await safe_edit_or_reply_universal(message_obj, message, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_SEARCH_USER)
            return
        
        # Получаем все подписки пользователя
        subscriptions = await get_all_subscriptions_by_user(user_id)
        
        # Получаем платежи пользователя
        payments = await get_payments_by_user(user_id, limit=10)
        
        # Форматируем даты
        first_seen = datetime.datetime.fromtimestamp(user['first_seen']).strftime('%d.%m.%Y %H:%M:%S')
        last_seen = datetime.datetime.fromtimestamp(user['last_seen']).strftime('%d.%m.%Y %H:%M:%S')
        
        # Статистика подписок
        active_subs = [s for s in subscriptions if s['status'] == 'active']
        expired_subs = [s for s in subscriptions if s['status'] == 'expired']
        deleted_subs = [s for s in subscriptions if s['status'] == 'deleted']
        
        lines = [
            f"{UIStyles.header('Информация о пользователе')}\n\n",
            f"<b>ID аккаунта:</b> <code>{user.get('user_id', user_id)}</code>\n",
        ]
        if user.get("telegram_id"):
            lines.append(f"<b>Telegram ID:</b> <code>{user['telegram_id']}</code>\n")
        if user.get("username"):
            lines.append(f"<b>Логин:</b> <code>{user['username']}</code>\n")
        lines.extend([
            f"<b>Первый запуск:</b> {first_seen}\n",
            f"<b>Последняя активность:</b> {last_seen}\n\n",
            f"<b>Подписки:</b>\n",
            f"   Всего: {len(subscriptions)}\n",
            f"   {UIEmojis.SUCCESS} Активных: {len(active_subs)}\n",
            f"   {UIEmojis.ERROR} Истекших: {len(expired_subs)}\n",
            f"   {UIEmojis.WARNING} Удаленных: {len(deleted_subs)}\n\n",
            f"<b>Платежи:</b> {len(payments)} (показано последних 10)\n",
        ])
        message = "".join(lines)
        
        # Кнопки действий
        keyboard_buttons = []
        
        if subscriptions:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    f"Все подписки ({len(subscriptions)})",
                    callback_data=f"admin_user_subs:{user_id}"
                )
            ])
        
        if payments:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    f"История платежей ({len(payments)})",
                    callback_data=f"admin_user_payments:{user_id}"
                )
            ])
        
        keyboard_buttons.append([NavigationBuilder.create_back_button()])
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        # Используем menu_chat_id и menu_message_id для редактирования, если они есть
        if menu_chat_id and menu_message_id:
            # Теперь у всех меню есть фото, используем safe_edit_message_with_photo
            from ...utils.message_helpers import safe_edit_message_with_photo
            bot = update.message.get_bot() if update.message else (update.callback_query.message.get_bot() if update.callback_query else None)
            if bot:
                try:
                    await safe_edit_message_with_photo(bot, menu_chat_id, menu_message_id, message, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_USER_INFO)
                except Exception as e:
                    logger.error(f"Не удалось отредактировать сообщение через safe_edit_message_with_photo: {e}")
                    # Fallback: используем обычный метод
                    message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
                    if message_obj:
                        await safe_edit_or_reply_universal(message_obj, message, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_USER_INFO)
            else:
                message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
                await safe_edit_or_reply_universal(message_obj, message, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_USER_INFO)
        else:
            message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
            await safe_edit_or_reply_universal(message_obj, message, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_USER_INFO)
        
        # Сохраняем user_id в context для дальнейших операций
        context.user_data['admin_selected_user_id'] = user_id
        
    except Exception as e:
        logger.exception("Ошибка в show_user_info")
        error_message = f"{UIEmojis.ERROR} Ошибка: {str(e)}"
        
        # Используем menu_chat_id и menu_message_id для редактирования, если они есть
        if menu_chat_id and menu_message_id:
            # Теперь у всех меню есть фото, используем safe_edit_message_with_photo
            from ...utils.message_helpers import safe_edit_message_with_photo
            bot = update.message.get_bot() if update.message else (update.callback_query.message.get_bot() if update.callback_query else None)
            if bot:
                try:
                    await safe_edit_message_with_photo(bot, menu_chat_id, menu_message_id, error_message, parse_mode="HTML", menu_type=MenuTypes.ADMIN_SEARCH_USER)
                except Exception as e:
                    logger.error(f"Не удалось отредактировать сообщение с ошибкой через safe_edit_message_with_photo: {e}")
                    # Fallback: отправляем новое сообщение
                    message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
                    if message_obj:
                        await safe_edit_or_reply_universal(message_obj, error_message, menu_type=MenuTypes.ADMIN_SEARCH_USER)
            else:
                message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
                if message_obj:
                    await safe_edit_or_reply_universal(message_obj, error_message, menu_type=MenuTypes.ADMIN_SEARCH_USER)
        else:
            message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
            if message_obj:
                await safe_edit_or_reply_universal(message_obj, error_message, menu_type=MenuTypes.ADMIN_SEARCH_USER)
            else:
                logger.error("Не удалось получить message_obj для отправки ошибки")


async def admin_user_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str = None):
    """Показывает все подписки пользователя"""
    if not await check_private_chat(update):
        return
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    if update.effective_user.id not in ADMIN_IDS:
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply_universal(message_obj, 'Нет доступа.', menu_type=MenuTypes.ADMIN_MENU)
        return
    
    if not user_id:
        user_id = context.user_data.get('admin_selected_user_id')
        if not user_id:
            # Пытаемся извлечь из callback_data
            if update.callback_query:
                parts = update.callback_query.data.split(':', 1)
                if len(parts) > 1:
                    user_id = parts[1]
    
    if not user_id:
        await safe_edit_or_reply_universal(
            update.message if update.message else update.callback_query.message,
            f"{UIEmojis.ERROR} Не указан user_id",
            menu_type=MenuTypes.ADMIN_SEARCH_USER
        )
        return
    
    try:
        subscriptions = await get_all_subscriptions_by_user(user_id)
        
        if not subscriptions:
            message = (
                f"{UIStyles.header('Подписки пользователя')}\n\n"
                f"{UIEmojis.WARNING} У пользователя <code>{user_id}</code> нет подписок."
            )
            keyboard = InlineKeyboardMarkup([
                [NavigationBuilder.create_back_button()]
            ])
            message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
            await safe_edit_or_reply_universal(message_obj, message, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_USER_SUBSCRIPTIONS)
            return
        
        message = f"{UIStyles.header('Подписки пользователя')}\n\n"
        keyboard_buttons = []
        
        for sub in subscriptions[:10]:  # Показываем максимум 10
            sub_id = sub['id']
            status = sub['status']
            name = sub.get('name', f"Подписка {sub_id}")
            expires_at = datetime.datetime.fromtimestamp(sub['expires_at']).strftime('%d.%m.%Y %H:%M')
            created_at = datetime.datetime.fromtimestamp(sub['created_at']).strftime('%d.%m.%Y')
            
            status_emoji = UIEmojis.SUCCESS if status == 'active' else (UIEmojis.ERROR if status == 'expired' else UIEmojis.WARNING)
            
            message += (
                f"{status_emoji} <b>{name}</b>\n"
                f"   ID: {sub_id} | Статус: {status}\n"
                f"   Создана: {created_at} | Истекает: {expires_at}\n\n"
            )
            
            keyboard_buttons.append([
                InlineKeyboardButton(
                    f"{status_emoji} {name[:30]}...",
                    callback_data=f"admin_sub_info:{sub_id}"
                )
            ])
        
        if len(subscriptions) > 10:
            message += f"\n{UIEmojis.WARNING} Показаны первые 10 из {len(subscriptions)} подписок\n"
        
        keyboard_buttons.append([NavigationBuilder.create_back_button()])
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply_universal(message_obj, message, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_USER_SUBSCRIPTIONS)
        
    except Exception as e:
        logger.exception("Ошибка в admin_user_subscriptions")
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply_universal(message_obj, f"{UIEmojis.ERROR} Ошибка: {str(e)}", menu_type=MenuTypes.ADMIN_SEARCH_USER)


async def admin_user_payments(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str = None):
    """Показывает платежи пользователя"""
    if not await check_private_chat(update):
        return
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    if update.effective_user.id not in ADMIN_IDS:
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply_universal(message_obj, 'Нет доступа.', menu_type=MenuTypes.ADMIN_MENU)
        return
    
    if not user_id:
        user_id = context.user_data.get('admin_selected_user_id')
        if not user_id:
            if update.callback_query:
                parts = update.callback_query.data.split(':', 1)
                if len(parts) > 1:
                    user_id = parts[1]
    
    if not user_id:
        await safe_edit_or_reply_universal(
            update.message if update.message else update.callback_query.message,
            f"{UIEmojis.ERROR} Не указан user_id",
            menu_type=MenuTypes.ADMIN_SEARCH_USER
        )
        return
    
    try:
        payments = await get_payments_by_user(user_id, limit=20)
        
        if not payments:
            message = (
                f"{UIStyles.header('Платежи пользователя')}\n\n"
                f"{UIEmojis.WARNING} У пользователя <code>{user_id}</code> нет платежей."
            )
            keyboard = InlineKeyboardMarkup([
                [NavigationBuilder.create_back_button()]
            ])
            message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
            await safe_edit_or_reply_universal(message_obj, message, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_USER_PAYMENTS)
            return
        
        message = f"{UIStyles.header('Платежи пользователя')}\n\n"
        
        for payment in payments:
            payment_id = payment['payment_id']
            status = payment['status']
            created_at = datetime.datetime.fromtimestamp(payment['created_at']).strftime('%d.%m.%Y %H:%M')
            meta = payment.get('meta', {})
            period = meta.get('type', 'unknown')
            price = meta.get('price', '0')
            
            status_emoji = UIEmojis.SUCCESS if status == 'succeeded' else (UIEmojis.WARNING if status == 'pending' else UIEmojis.ERROR)
            
            message += (
                f"{status_emoji} <b>{payment_id[:20]}...</b>\n"
                f"   Статус: {status} | Период: {period} | Цена: {price}₽\n"
                f"   Создан: {created_at}\n\n"
            )
        
        keyboard = InlineKeyboardMarkup([
            [NavigationBuilder.create_back_button()]
        ])
        
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply_universal(message_obj, message, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_USER_PAYMENTS)
        
    except Exception as e:
        logger.exception("Ошибка в admin_user_payments")
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply_universal(message_obj, f"{UIEmojis.ERROR} Ошибка: {str(e)}", menu_type=MenuTypes.ADMIN_SEARCH_USER)

