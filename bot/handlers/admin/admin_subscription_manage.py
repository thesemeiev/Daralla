"""
Админ-панель для управления подписками
"""
import logging
import datetime
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from ...utils import UIEmojis, UIStyles, safe_edit_or_reply_universal, check_private_chat
from ...navigation import NavStates, CallbackData, MenuTypes, NavigationBuilder
from ...db import (
    get_subscription_servers, update_subscription_status,
    update_subscription_expiry, get_subscription_by_token,
    update_subscription_device_limit
)

logger = logging.getLogger(__name__)

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


async def admin_subscription_info(update: Update, context: ContextTypes.DEFAULT_TYPE, subscription_id: int = None):
    """Показывает детальную информацию о подписке"""
    if not await check_private_chat(update):
        return
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    if update.effective_user.id not in ADMIN_IDS:
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply_universal(message_obj, 'Нет доступа.', menu_type=MenuTypes.ADMIN_MENU)
        return
    
    if not subscription_id:
        if update.callback_query:
            parts = update.callback_query.data.split(':', 1)
            if len(parts) > 1:
                try:
                    subscription_id = int(parts[1])
                except ValueError:
                    await update.callback_query.answer("Неверный ID подписки", show_alert=True)
                    return
    
    if not subscription_id:
        await safe_edit_or_reply_universal(
            update.message if update.message else update.callback_query.message,
            f"{UIEmojis.ERROR} Не указан ID подписки",
            menu_type=MenuTypes.ADMIN_MENU
        )
        return
    
    try:
        # Получаем подписку (нужен user_id для проверки)
        # Для админа получаем через токен или напрямую из БД
        from ...db.subscribers_db import get_all_active_subscriptions
        all_subs = await get_all_active_subscriptions()
        sub = next((s for s in all_subs if s['id'] == subscription_id), None)
        
        if not sub:
            # Пробуем получить все подписки (включая истекшие)
            from ...db import get_all_subscriptions_by_user
            # Нужно найти через поиск по всем пользователям
            async def find_subscription():
                from ...db import get_all_user_ids
                user_ids = await get_all_user_ids()
                for uid in user_ids[:100]:  # Ограничиваем поиск
                    subs = await get_all_subscriptions_by_user(uid)
                    found = next((s for s in subs if s['id'] == subscription_id), None)
                    if found:
                        return found
                return None
            
            sub = await find_subscription()
        
        if not sub:
            message = (
                f"{UIEmojis.ERROR} <b>Подписка не найдена</b>\n\n"
                f"Подписка с ID <code>{subscription_id}</code> не найдена в базе данных."
            )
            keyboard = InlineKeyboardMarkup([
                [NavigationBuilder.create_back_button()]
            ])
            message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
            await safe_edit_or_reply_universal(message_obj, message, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_MENU)
            return
        
        # Получаем серверы подписки
        servers = await get_subscription_servers(subscription_id)
        
        # Форматируем время
        created_at = datetime.datetime.fromtimestamp(sub['created_at']).strftime('%d.%m.%Y %H:%M:%S')
        expires_at = datetime.datetime.fromtimestamp(sub['expires_at']).strftime('%d.%m.%Y %H:%M:%S')
        current_time = datetime.datetime.now()
        is_expired = sub['expires_at'] < int(current_time.timestamp())
        is_active = sub['status'] == 'active' and not is_expired
        
        status_emoji = UIEmojis.SUCCESS if is_active else (UIEmojis.ERROR if is_expired else UIEmojis.WARNING)
        status_text = "Активна" if is_active else f"Неактивна (status: {sub['status']}, expired: {is_expired})"
        
        message = (
            f"{UIStyles.header('Информация о подписке')}\n\n"
            f"{status_emoji} <b>Статус:</b> {status_text}\n\n"
            f"<b>ID подписки:</b> {sub['id']}\n"
            f"<b>Пользователь:</b> <code>{sub['user_id']}</code>\n"
            f"<b>Название:</b> {sub.get('name', 'Без названия')}\n"
            f"<b>Токен:</b> <code>{sub['subscription_token']}</code>\n"
            f"<b>Период:</b> {sub['period']}\n"
            f"<b>Устройств:</b> {sub['device_limit']}\n"
            f"<b>Цена:</b> {sub['price']}₽\n\n"
            f"<b>Создана:</b> {created_at}\n"
            f"<b>Истекает:</b> {expires_at}\n"
            f"<b>Текущее время:</b> {current_time.strftime('%d.%m.%Y %H:%M:%S')}\n\n"
            f"<b>Серверов привязано:</b> {len(servers)}\n"
        )
        
        if servers:
            message += f"\n<b>Серверы:</b>\n"
            for i, server in enumerate(servers, 1):
                message += f"{i}. {server['server_name']} ({server['client_email']})\n"
        
        # Кнопки управления
        keyboard_buttons = []
        
        if is_active:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    f"⏰ Продлить на 30 дней",
                    callback_data=f"admin_sub_extend:{subscription_id}:30"
                )
            ])
            keyboard_buttons.append([
                InlineKeyboardButton(
                    f"⏰ Продлить на 90 дней",
                    callback_data=f"admin_sub_extend:{subscription_id}:90"
                )
            ])
        
        if sub['status'] != 'canceled':
            keyboard_buttons.append([
                InlineKeyboardButton(
                    f"Отменить подписку",
                    callback_data=f"admin_sub_cancel:{subscription_id}"
                )
            ])
        
        # Кнопка для изменения лимита IP
        keyboard_buttons.append([
            InlineKeyboardButton(
                f"🔢 Изменить лимит IP",
                callback_data=f"admin_sub_change_limit:{subscription_id}"
            )
        ])
        
        # Кнопка "Назад" должна вести на список подписок пользователя, а не в админ панель
        user_id = sub.get('user_id')
        if user_id:
            keyboard_buttons.append([
                InlineKeyboardButton(
                    "← Назад",
                    callback_data=f"admin_user_subs:{user_id}"
                )
            ])
        else:
            keyboard_buttons.append([NavigationBuilder.create_back_button()])
        keyboard = InlineKeyboardMarkup(keyboard_buttons)
        
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply_universal(message_obj, message, reply_markup=keyboard, parse_mode="HTML", menu_type=MenuTypes.ADMIN_SUBSCRIPTION_INFO)
        
    except Exception as e:
        logger.exception("Ошибка в admin_subscription_info")
        message_obj = update.message if update.message else (update.callback_query.message if update.callback_query else None)
        await safe_edit_or_reply_universal(message_obj, f"{UIEmojis.ERROR} Ошибка: {str(e)}", menu_type=MenuTypes.ADMIN_MENU)


async def admin_extend_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE, subscription_id: int = None, days: int = None):
    """Продлевает подписку на указанное количество дней"""
    if not await check_private_chat(update):
        return
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    subscription_manager = globals_dict['subscription_manager']
    
    if update.effective_user.id not in ADMIN_IDS:
        await update.callback_query.answer("Нет доступа", show_alert=True)
        return
    
    if not subscription_id or not days:
        if update.callback_query:
            parts = update.callback_query.data.split(':')
            if len(parts) >= 3:
                try:
                    subscription_id = int(parts[1])
                    days = int(parts[2])
                except ValueError:
                    await update.callback_query.answer("Неверные параметры", show_alert=True)
                    return
    
    if not subscription_id or not days:
        await update.callback_query.answer("Не указаны параметры", show_alert=True)
        return
    
    try:
        await update.callback_query.answer("Продлеваю подписку...", show_alert=False)
        
        # Получаем подписку
        from ...db.subscribers_db import get_all_active_subscriptions
        all_subs = await get_all_active_subscriptions()
        sub = next((s for s in all_subs if s['id'] == subscription_id), None)
        
        if not sub:
            message_obj = update.callback_query.message if update.callback_query else None
            keyboard = InlineKeyboardMarkup([
                [NavigationBuilder.create_back_button()]
            ])
            await safe_edit_or_reply_universal(
                message_obj,
                f"{UIEmojis.ERROR} Подписка не найдена",
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type=MenuTypes.ADMIN_SUBSCRIPTION_INFO
            )
            return
        
        # Обновляем время истечения
        current_expires = sub['expires_at']
        new_expires = current_expires + (days * 24 * 60 * 60)
        await update_subscription_expiry(subscription_id, new_expires)
        
        # Синхронизируем с серверами
        if subscription_manager:
            servers = await get_subscription_servers(subscription_id)
            device_limit = sub.get('device_limit', 1)  # Получаем device_limit из подписки
            for server in servers:
                try:
                    await subscription_manager.ensure_client_on_server(
                        subscription_id=subscription_id,
                        server_name=server['server_name'],
                        client_email=server['client_email'],
                        user_id=sub['user_id'],
                        expires_at=new_expires,
                        token=sub['subscription_token'],
                        device_limit=device_limit  # Передаем device_limit для синхронизации limitIp
                    )
                except Exception as e:
                    logger.error(f"Ошибка синхронизации сервера {server['server_name']}: {e}")
        
        new_expires_str = datetime.datetime.fromtimestamp(new_expires).strftime('%d.%m.%Y %H:%M:%S')
        
        message = (
            f"{UIStyles.header('Подписка продлена')}\n\n"
            f"{UIEmojis.SUCCESS} Подписка <b>{sub.get('name', f'#{subscription_id}')}</b> продлена на {days} дней.\n\n"
            f"<b>Новая дата истечения:</b> {new_expires_str}\n\n"
            f"{UIStyles.description('Время синхронизировано на всех серверах.')}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Информация о подписке", callback_data=f"{CallbackData.ADMIN_SUB_INFO}{subscription_id}")],
            [NavigationBuilder.create_back_button()]
        ])
        
        message_obj = update.callback_query.message if update.callback_query else None
        await safe_edit_or_reply_universal(
            message_obj,
            message,
            reply_markup=keyboard,
            parse_mode="HTML",
            menu_type=MenuTypes.ADMIN_SUBSCRIPTION_INFO
        )
        
        logger.info(f"Админ {update.effective_user.id} продлил подписку {subscription_id} на {days} дней")
        
    except Exception as e:
        logger.exception("Ошибка в admin_extend_subscription")
        await update.callback_query.answer(f"Ошибка: {str(e)}", show_alert=True)


async def admin_cancel_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE, subscription_id: int = None):
    """Отменяет подписку"""
    if not await check_private_chat(update):
        return
    
    globals_dict = get_globals()
    ADMIN_IDS = globals_dict['ADMIN_IDS']
    
    if update.effective_user.id not in ADMIN_IDS:
        await update.callback_query.answer("Нет доступа", show_alert=True)
        return
    
    if not subscription_id:
        if update.callback_query:
            parts = update.callback_query.data.split(':', 1)
            if len(parts) > 1:
                try:
                    subscription_id = int(parts[1])
                except ValueError:
                    await update.callback_query.answer("Неверный ID подписки", show_alert=True)
                    return
    
    if not subscription_id:
        await update.callback_query.answer("Не указан ID подписки", show_alert=True)
        return
    
    try:
        await update.callback_query.answer("Отменяю подписку...", show_alert=False)
        
        # Получаем подписку
        from ...db.subscribers_db import get_all_active_subscriptions
        all_subs = await get_all_active_subscriptions()
        sub = next((s for s in all_subs if s['id'] == subscription_id), None)
        
        if not sub:
            message_obj = update.callback_query.message if update.callback_query else None
            keyboard = InlineKeyboardMarkup([
                [NavigationBuilder.create_back_button()]
            ])
            await safe_edit_or_reply_universal(
                message_obj,
                f"{UIEmojis.ERROR} Подписка не найдена",
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type=MenuTypes.ADMIN_SUBSCRIPTION_INFO
            )
            return
        
        # Обновляем статус
        await update_subscription_status(subscription_id, 'canceled')
        
        message = (
            f"{UIStyles.header('Подписка отменена')}\n\n"
            f"{UIEmojis.SUCCESS} Подписка <b>{sub.get('name', f'#{subscription_id}')}</b> отменена.\n\n"
            f"{UIStyles.description('Статус подписки изменен на canceled.')}"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Информация о подписке", callback_data=f"{CallbackData.ADMIN_SUB_INFO}{subscription_id}")],
            [NavigationBuilder.create_back_button()]
        ])
        
        message_obj = update.callback_query.message if update.callback_query else None
        await safe_edit_or_reply_universal(
            message_obj,
            message,
            reply_markup=keyboard,
            parse_mode="HTML",
            menu_type=MenuTypes.ADMIN_SUBSCRIPTION_INFO
        )
        
        logger.info(f"Админ {update.effective_user.id} отменил подписку {subscription_id}")
        
    except Exception as e:
        logger.exception("Ошибка в admin_cancel_subscription")
        await update.callback_query.answer(f"Ошибка: {str(e)}", show_alert=True)

