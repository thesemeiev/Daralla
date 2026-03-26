"""
Обработчики платежей из webhook'ов YooKassa
"""
import logging
import json
import datetime
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

from ...db import get_payment_by_id, update_payment_status, update_payment_activation
from ...db.users_db import get_telegram_chat_id_for_notification
from ...utils import (
    UIEmojis, UIStyles, UIMessages,
    safe_edit_message_with_photo, safe_send_message_with_photo
)
from ...navigation import MenuTypes

logger = logging.getLogger(__name__)


def get_globals():
    """Получает сервисы из AppContext."""
    from ...app_context import get_ctx
    ctx = get_ctx()
    return {
        'notification_manager': ctx.notification_manager,
        'subscription_manager': ctx.subscription_manager,
        'remnawave_service': ctx.remnawave_service,
    }


async def process_payment_webhook(bot_app, payment_id, status):
    """Обрабатывает платеж из webhook'а (YooKassa и CryptoCloud)."""
    try:
        # Нормализуем статус: CryptoCloud может присылать "cancelled"
        if status == "cancelled":
            status = "canceled"
        # Получаем информацию о платеже из базы данных
        payment_info = await get_payment_by_id(payment_id)
        if not payment_info:
            logger.warning(f"Платеж {payment_id} не найден в базе данных")
            return
        
        # Проверяем, не обработан ли уже этот платеж
        current_status = payment_info.get('status', 'pending')
        is_activated = payment_info.get('activated', 0)
        
        if status == 'succeeded' and current_status == 'succeeded' and is_activated == 1:
            logger.info(f"Платеж {payment_id} уже обработан, пропускаем повторную обработку")
            return
        
        user_id = payment_info['user_id']
        raw_meta = payment_info.get('meta')
        if raw_meta is None:
            meta = {}
        elif isinstance(raw_meta, dict):
            meta = raw_meta
        elif isinstance(raw_meta, str):
            try:
                meta = json.loads(raw_meta) if raw_meta.strip() else {}
            except (json.JSONDecodeError, AttributeError):
                meta = {}
        else:
            meta = {}
        
        logger.info(f"Обработка webhook платежа: payment_id={payment_id}, user_id={user_id}, status={status}, current_status={current_status}, activated={is_activated}")
        
        # Обрабатываем платеж в зависимости от статуса
        if status == 'succeeded':
            # Успешная оплата - создаем или продлеваем подписку
            await process_successful_payment(bot_app, payment_id, user_id, meta)
        elif status in ['canceled', 'refunded']:
            # Отмененная/возвращенная оплата
            await process_canceled_payment(bot_app, payment_id, user_id, meta, status)
        elif status not in ['pending']:
            # Любой другой неуспешный статус
            await process_failed_payment(bot_app, payment_id, user_id, meta, status)
        
    except (KeyError, TypeError, ValueError, RuntimeError) as e:
        logger.error(f"Ошибка обработки webhook платежа {payment_id}: {e}")


async def process_successful_payment(bot_app, payment_id, user_id, meta):
    """Обрабатывает успешный платеж"""
    try:
        period = meta.get('type', 'month')
        device_limit = int(meta.get('device_limit', 1))
        # Получаем message_id из мета-данных платежа
        message_id = meta.get('message_id')
        
        # Проверяем, это продление или новая покупка
        is_extension = period.startswith('extend_')
        if is_extension:
            # Обработка продления подписки
            await process_extension_payment(bot_app, payment_id, user_id, meta, message_id)
        else:
            # Обработка новой покупки подписки
            await process_new_purchase_payment(bot_app, payment_id, user_id, meta, message_id)
            
    except (KeyError, TypeError, ValueError, RuntimeError) as e:
        logger.error(f"Ошибка обработки успешного платежа {payment_id}: {e}")


async def process_extension_payment(bot_app, payment_id, user_id, meta, message_id):
    """Обрабатывает продление подписки"""
    try:
        chat_id = await get_telegram_chat_id_for_notification(user_id)
        period = meta.get('type', 'month')
        # Убираем префиксы: extend_sub_month -> month, extend_sub_3month -> 3month
        actual_period = period
        if period.startswith('extend_sub_'):
            actual_period = period.replace('extend_sub_', '', 1)
        elif period.startswith('extend_'):
            actual_period = period.replace('extend_', '', 1)
        days = 90 if actual_period == '3month' else 30
        
        # Проверяем, это продление подписки
        is_subscription_extension = period.startswith('extend_sub_')
        extension_subscription_id = meta.get('extension_subscription_id')
        
        if is_subscription_extension:
            # Продление подписки
            logger.info(f"Обработка продления подписки: subscription_id={extension_subscription_id}, period={period}, actual_period={actual_period}, days={days}")
            
            if not extension_subscription_id:
                logger.error(f"Не найден subscription_id для продления в meta: {meta}")
                await update_payment_status(payment_id, 'failed')
                return
            
            globals_dict = get_globals()
            subscription_manager = globals_dict.get('subscription_manager')
            if not subscription_manager:
                logger.error("subscription_manager не доступен")
                await update_payment_status(payment_id, 'failed')
                return
            
            # Проверяем, что подписка принадлежит пользователю
            from ...db.subscriptions_db import get_subscription_by_id
            sub = await get_subscription_by_id(extension_subscription_id, user_id)
            
            if not sub:
                logger.error(f"Попытка продлить чужую подписку: user_id={user_id}, subscription_id={extension_subscription_id}")
                await update_payment_status(payment_id, 'failed')
                return

            if sub.get("status") == "deleted":
                logger.warning(
                    "Продление удалённой подписки: subscription_id=%s, user_id=%s, payment_id=%s. Платёж засчитан, подписка не продлевается.",
                    extension_subscription_id, user_id, payment_id,
                )
                await update_payment_status(payment_id, "succeeded")
                await update_payment_activation(payment_id, 1)
                return
            
            # Шаг 1: Вычисляем новое время истечения и обновляем БД
            import time
            current_time = int(time.time())
            if sub:
                # Если продлевают пробную (price=0) — обновляем price, чтобы конверсия учитывалась
                sub_price = float(sub.get('price') or 0)
                if sub_price == 0:
                    from ...prices_config import PRICES
                    paid_price = PRICES.get(actual_period, 150)
                    from ...db.subscriptions_db import update_subscription_price
                    await update_subscription_price(extension_subscription_id, float(paid_price))
                    logger.info(f"Пробная подписка {extension_subscription_id} конвертирована в платную (price={paid_price})")

                # Вычисляем новое время истечения
                current_expires_at = sub['expires_at']
                # Если подписка уже истекла, начинаем с текущего времени, иначе продлеваем от текущего expires_at
                base_time = max(current_expires_at, current_time)
                new_expires_at = base_time + days * 24 * 60 * 60

                # Обновляем expires_at в БД ПЕРЕД синхронизацией серверов
                from ...db.subscriptions_db import update_subscription_expiry
                await update_subscription_expiry(extension_subscription_id, new_expires_at)
                logger.info(f"Подписка {extension_subscription_id} продлена до {new_expires_at} в БД")
            else:
                # Если подписка не найдена, используем текущее время + дни
                new_expires_at = current_time + days * 24 * 60 * 60
                logger.warning(f"Подписка {extension_subscription_id} не найдена в БД, используем расчетное время: {new_expires_at}")
            
            # Шаг 2: Обновляем runtime в RemnaWave
            device_limit = sub.get('device_limit', 1) if sub else 1
            ok = await subscription_manager.ensure_access(
                subscription_id=extension_subscription_id,
                user_id=user_id,
                expires_at=new_expires_at,
                token=sub['subscription_token'] if sub else '',
                device_limit=device_limit
            )
            if not ok:
                logger.error("Не удалось обновить runtime в RemnaWave для %s", extension_subscription_id)
                await update_payment_status(payment_id, 'failed')
                if message_id and chat_id:
                    error_message = (
                        f"{UIStyles.header('Ошибка продления подписки')}\n\n"
                        f"{UIEmojis.ERROR} <b>Не удалось продлить подписку!</b>\n\n"
                        f"<b>Причина:</b> Не удалось обновить доступ в RemnaWave\n\n"
                        f"{UIStyles.description('Попробуйте позже или обратитесь в поддержку')}"
                    )
                    # Создаем кнопку для открытия мини-приложения
                    from ...utils import UIButtons
                    webapp_button = UIButtons.create_webapp_button(
                        action='subscriptions'
                    )
                    
                    buttons = []
                    if webapp_button:
                        buttons.append([webapp_button])
                    
                    keyboard = InlineKeyboardMarkup(buttons) if buttons else None
                    await safe_edit_message_with_photo(
                        bot_app.bot,
                        chat_id=chat_id,
                        message_id=message_id,
                        text=error_message,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        menu_type=MenuTypes.PAYMENT_FAILED
                    )
                return

            await update_payment_status(payment_id, 'succeeded')
            await update_payment_activation(payment_id, 1)

            try:
                from bot.events import EVENTS_MODULE_ENABLED, on_payment_success as events_on_payment_success
                if EVENTS_MODULE_ENABLED:
                    await events_on_payment_success(user_id, payment_id, meta)
            except (ImportError, RuntimeError, ValueError) as events_e:
                logger.debug("events.on_payment_success (extension): %s", events_e)
            
            # Отправляем уведомление о продлении подписки
            try:
                expiry_time = datetime.datetime.fromtimestamp(new_expires_at)
                expiry_str = expiry_time.strftime('%d.%m.%Y %H:%M')
                period_text = "3 месяца" if actual_period == "3month" else "1 месяц"
                
                extension_message = (
                    f"{UIStyles.header('Подписка продлена!')}\n\n"
                    f"{UIEmojis.SUCCESS} <b>Ваша подписка успешно продлена</b>\n\n"
                    f"<b>Период:</b> {period_text}\n"
                    f"<b>Новое окончание:</b> {expiry_str}\n"
                    f"<b>Runtime:</b> RemnaWave обновлен\n\n"
                )
                extension_message += f"{UIStyles.description('Подписка активна и готова к использованию.')}"
                
                if chat_id:
                    # Создаем кнопку для открытия мини-приложения
                    from ...utils import UIButtons
                    webapp_button = UIButtons.create_webapp_button(
                        action='subscription',
                        params=extension_subscription_id
                    )
                    
                    buttons = []
                    if webapp_button:
                        buttons.append([webapp_button])
                    
                    keyboard = InlineKeyboardMarkup(buttons) if buttons else None
                    
                    if message_id:
                        await safe_edit_message_with_photo(
                            bot_app.bot,
                            chat_id=chat_id,
                            message_id=message_id,
                            text=extension_message,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            menu_type=MenuTypes.PAYMENT_SUCCESS
                        )
                        logger.info(f"Отредактировано сообщение о продлении подписки {extension_subscription_id} пользователю {user_id}")
                    else:
                        await safe_send_message_with_photo(
                            bot_app.bot,
                            chat_id=chat_id,
                            text=extension_message,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                            menu_type=MenuTypes.PAYMENT_SUCCESS
                        )
                        logger.info(f"Отправлено новое сообщение о продлении подписки {extension_subscription_id} пользователю {user_id}")
                    
            except (RuntimeError, ValueError, TypeError) as e:
                logger.error(f"Ошибка отправки уведомления о продлении подписки: {e}")
            
            return
        else:
            # Это не продление подписки - ошибка
            logger.error(f"Неизвестный тип продления: period={period}, meta={meta}")
            await update_payment_status(payment_id, 'failed')
            return
                    
    except (KeyError, TypeError, ValueError, RuntimeError) as e:
        logger.error(f"Ошибка обработки продления подписки {payment_id}: {e}")


async def process_new_purchase_payment(bot_app, payment_id, user_id, meta, message_id):
    """Обрабатывает новую покупку - создаёт подписку и runtime в RemnaWave"""
    try:
        chat_id = await get_telegram_chat_id_for_notification(user_id)
        period = meta.get('type', 'month')
        days = 90 if period == '3month' else 30
        device_limit = int(meta.get('device_limit', 1))
        unique_email = meta.get('unique_email')
        
        logger.info(f"Обработка новой покупки: period={period}, days={days}, email={unique_email}")
        
        if not unique_email:
            logger.error(f"Не найден unique_email в meta: {meta}")
            await update_payment_status(payment_id, 'failed')
            return
        
        globals_dict = get_globals()
        subscription_manager = globals_dict.get('subscription_manager')
        if not subscription_manager:
            logger.error("subscription_manager не доступен")
            await update_payment_status(payment_id, 'failed')
            return

        price = float(meta.get('price', '0') or 0)
        sub_dict = None
        token = None
        subscription_created = False
        try:
            sub_dict, token = await subscription_manager.create_subscription_for_user(
                user_id=str(user_id),
                period=period,
                device_limit=device_limit,
                price=price,
            )
            subscription_created = True
            logger.info(f"Подписка создана: sub_id={sub_dict['id']}, token={token}")
            
            # Используем правильный формат email: {user_id}_{subscription_id}
            # Вместо UUID из метаданных платежа используем реальный subscription_id
            unique_email = f"{user_id}_{sub_dict['id']}"
            logger.info(f"Используется правильный формат email: {unique_email} (вместо UUID из метаданных)")
        except Exception as sub_e:
            logger.error(f"Ошибка при создании подписки для user_id={user_id}: {sub_e}")
            await update_payment_status(payment_id, 'failed')
            return
        
        expires_at = sub_dict.get('expires_at') if sub_dict else None
        if not expires_at:
            import time
            expires_at = int(time.time()) + days * 24 * 60 * 60

        ok = await subscription_manager.ensure_access(
            subscription_id=sub_dict["id"],
            user_id=user_id,
            expires_at=expires_at,
            token=token,
            device_limit=device_limit,
        )
        if not ok:
            logger.error("Не удалось создать runtime доступ в RemnaWave")
            if subscription_created and sub_dict:
                try:
                    from ...db.subscriptions_db import update_subscription_status
                    await update_subscription_status(sub_dict['id'], 'deleted')
                    logger.info(f"Подписка {sub_dict['id']} удалена из-за ошибки создания клиентов (компенсирующая транзакция)")
                except Exception as rollback_e:
                    logger.error(f"Ошибка отката подписки {sub_dict['id']}: {rollback_e}")
            
            await update_payment_status(payment_id, 'failed')
            # Уведомляем пользователя
            try:
                error_message = (
                    f"{UIStyles.header('Ошибка создания подписки')}\n\n"
                    f"{UIEmojis.ERROR} <b>Не удалось создать подписку!</b>\n\n"
                    f"<b>Причина:</b> Не удалось создать доступ в RemnaWave\n\n"
                    f"{UIStyles.description('Попробуйте позже или обратитесь в поддержку')}"
                )
                if message_id and chat_id:
                    from ...utils import UIButtons
                    webapp_button = UIButtons.create_webapp_button(
                        action='subscriptions'
                    )
                    buttons = []
                    if webapp_button:
                        buttons.append([webapp_button])
                    keyboard = InlineKeyboardMarkup(buttons) if buttons else None
                    await safe_edit_message_with_photo(
                        bot_app.bot,
                        chat_id=chat_id,
                        message_id=message_id,
                        text=error_message,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        menu_type=MenuTypes.PAYMENT_FAILED
                    )
            except Exception as e:
                logger.error(f"Ошибка отправки сообщения об ошибке: {e}")
            return

        await update_payment_status(payment_id, 'succeeded')
        await update_payment_activation(payment_id, 1)

        try:
            from bot.events import EVENTS_MODULE_ENABLED, on_payment_success as events_on_payment_success
            if EVENTS_MODULE_ENABLED:
                await events_on_payment_success(user_id, payment_id, meta)
        except Exception as events_e:
            logger.debug("events.on_payment_success (new purchase): %s", events_e)
        
        logger.info(f"Подписка {sub_dict['id']} создана в RemnaWave runtime")
        
        # Шаг 5: Отправляем информацию о подписке пользователю
        try:
            # Вычисляем время истечения
            expiry_time = datetime.datetime.now() + datetime.timedelta(days=days)
            expiry_str = expiry_time.strftime('%d.%m.%Y %H:%M')
            expiry_timestamp = int(expiry_time.timestamp())

            # Получаем WEBHOOK_URL для формирования полного URL подписки
            # WEBHOOK_URL должен быть публичным URL вашего webhook сервера (например, через ngrok или домен)
            # Формат: http://your-domain.com или https://your-domain.com
            import os
            webhook_url = os.getenv("WEBHOOK_URL", "").rstrip("/")

            try:
                from ...app_context import get_ctx
                vpn_brand_name = get_ctx().vpn_brand_name
            except RuntimeError:
                vpn_brand_name = os.getenv('VPN_BRAND_NAME', 'Daralla VPN').strip()
            
            # Формируем subscription URL
            # Для Happ клиента лучше использовать поддомен (как делают другие разработчики: auth.zkodes.ru)
            # Happ использует домен из URL как название группы подписки
            import urllib.parse
            
            # Проверяем, есть ли специальный URL для подписок (поддомен)
            subscription_base_url = os.getenv("SUBSCRIPTION_URL", "").rstrip("/")
            
            # Если SUBSCRIPTION_URL не установлен, извлекаем базовый URL из WEBHOOK_URL
            # (убираем путь /webhook/yookassa, оставляем только домен)
            if subscription_base_url:
                base_url = subscription_base_url
            elif webhook_url:
                # Извлекаем базовый URL (домен) из WEBHOOK_URL
                parsed = urllib.parse.urlparse(webhook_url)
                base_url = f"{parsed.scheme}://{parsed.netloc}"
            else:
                base_url = None
            
            if base_url:
                # Для Happ клиента используем поддомен в URL (например: daralla-vpn.ghosttunnel.space)
                # Happ автоматически использует поддомен (или первую часть) как название группы
                # Параметр name убираем, так как он может вызывать проблемы с эмодзи и 502 ошибки
                # Поддомен в URL - это основной способ для Happ
                subscription_url = f"{base_url}/sub/{token}"
                logger.info(f"Subscription URL сформирован: {subscription_url}")
            else:
                # Если WEBHOOK_URL не установлен, предупреждаем
                # В продакшене это должно быть обязательно установлено!
                subscription_url = f"http://localhost:5000/sub/{token}"  # Временный fallback для разработки
                logger.warning(
                    "⚠️ WEBHOOK_URL не установлен! "
                    "Установите переменную окружения WEBHOOK_URL с публичным URL вашего webhook сервера. "
                    "Например: WEBHOOK_URL=https://your-domain.com или через ngrok: WEBHOOK_URL=https://xxxx.ngrok.io"
                )
            
            # Формируем сообщение о подписке
            period_text = "3 месяца" if period == "3month" else "1 месяц"
            subscription_message = (
                f"{UIStyles.header('Подписка активирована!')}\n\n"
                f"{UIEmojis.SUCCESS} <b>Ваша подписка успешно создана</b>\n\n"
                f"<b>Период:</b> {period_text}\n"
                f"<b>Окончание:</b> {expiry_str}\n"
                f"<b>Панель:</b> RemnaWave\n"
                f"<b>Устройств:</b> {device_limit}\n\n"
                f"{UIStyles.header('Ссылка на подписку:')}\n"
                f"<code>{subscription_url}</code>\n\n"
                f"{UIStyles.description('Используйте эту ссылку для импорта в VPN-клиент. Подписка включает все доступные серверы.')}"
            )
            
            # Создаем кнопку для открытия мини-приложения
            from ...utils import UIButtons
            webapp_button = UIButtons.create_webapp_button(
                action='subscription',
                params=sub_dict['id'] if sub_dict else None
            )
            
            buttons = []
            if webapp_button:
                buttons.append([webapp_button])
            
            keyboard = InlineKeyboardMarkup(buttons) if buttons else None
            
            # Получаем message_id из мета-данных платежа
            payment_info = await get_payment_by_id(payment_id)
            stored_message_id = None
            if payment_info and payment_info.get('meta'):
                if isinstance(payment_info['meta'], dict):
                    stored_message_id = payment_info['meta'].get('message_id')
                elif isinstance(payment_info['meta'], str):
                    try:
                        meta_dict = json.loads(payment_info['meta'])
                        stored_message_id = meta_dict.get('message_id')
                    except (TypeError, ValueError, json.JSONDecodeError):
                        pass
            
            # Используем message_id из webhook или из базы данных
            # Для платежей из мини-приложения message_id может быть None - не отправляем сообщение в бот
            actual_message_id = message_id or stored_message_id
            
            if chat_id and actual_message_id:
                try:
                    await safe_edit_message_with_photo(
                        bot_app.bot,
                        chat_id=chat_id,
                        message_id=actual_message_id,
                        text=subscription_message,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        menu_type=MenuTypes.PAYMENT_SUCCESS
                    )
                    logger.info(f"Отредактировано сообщение с оплатой {actual_message_id} на информацию о подписке")
                except (RuntimeError, ValueError, TypeError) as edit_error:
                    error_str = str(edit_error).lower()
                    if "no text" in error_str or "can't be edited" in error_str:
                        logger.debug(f"Сообщение {actual_message_id} уже отредактировано как медиа, пропускаем: {edit_error}")
                    else:
                        logger.error(f"Ошибка редактирования сообщения {actual_message_id}: {edit_error}")
                    await safe_send_message_with_photo(
                        bot_app.bot,
                        chat_id=chat_id,
                        text=subscription_message,
                        reply_markup=keyboard,
                        parse_mode="HTML",
                        menu_type=MenuTypes.PAYMENT_SUCCESS
                    )
                    logger.info(f"Отправлено новое сообщение с подпиской для user_id={user_id}")
            elif not actual_message_id:
                logger.info(f"Платеж из мини-приложения для user_id={user_id} - сообщение в бот не отправляется (нет message_id)")
                
        except (RuntimeError, ValueError, TypeError, KeyError) as e:
            logger.error(f"Ошибка отправки информации о подписке пользователю: {e}")
            
    except (KeyError, TypeError, ValueError, RuntimeError) as e:
        logger.error(f"Ошибка обработки новой покупки {payment_id}: {e}")
        await update_payment_status(payment_id, 'failed')


async def process_canceled_payment(bot_app, payment_id, user_id, meta, status):
    """Обрабатывает отмененный/возвращенный платеж. В БД сохраняем реальный статус (canceled/refunded) для корректного отображения на фронте."""
    try:
        # Сохраняем фактический статус, чтобы API отдал его фронту и пользователь видел «отменен»/«возвращен»
        await update_payment_status(payment_id, status if status in ('canceled', 'refunded') else 'failed')
        await update_payment_activation(payment_id, 0)
        
        message_id = meta.get('message_id')
        chat_id = await get_telegram_chat_id_for_notification(user_id)
        if message_id and chat_id:
            error_message = (
                f"{UIStyles.header('Ошибка оплаты')}\n\n"
                f"{UIEmojis.ERROR} <b>Платеж не прошел!</b>\n\n"
                f"<b>Причина:</b> Платеж был отменен или возвращен\n"
                f"<b>Статус:</b> {status}\n\n"
                f"{UIStyles.description('Попробуйте оплатить заново или обратитесь в поддержку')}"
            )
            from ...utils import UIButtons
            webapp_button = UIButtons.create_webapp_button(action='subscriptions', text="Открыть в приложении")
            buttons = [[webapp_button]] if webapp_button else []
            keyboard = InlineKeyboardMarkup(buttons) if buttons else None
            await safe_edit_message_with_photo(
                bot_app.bot,
                chat_id=chat_id,
                message_id=message_id,
                text=error_message,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type=MenuTypes.PAYMENT_FAILED
            )
            logger.info(f"Отправлено сообщение об ошибке оплаты пользователю {user_id}")
                    
    except (RuntimeError, ValueError, TypeError, KeyError) as e:
        logger.error(f"Ошибка обработки отмененного платежа {payment_id}: {e}")


async def process_failed_payment(bot_app, payment_id, user_id, meta, status):
    """Обрабатывает неудачный платеж"""
    try:
        await update_payment_status(payment_id, 'failed')
        await update_payment_activation(payment_id, 0)
        
        chat_id = await get_telegram_chat_id_for_notification(user_id)
        period = meta.get('type', 'month')
        is_extension = period.startswith('extend_')
        
        message_id = meta.get('message_id')
        if message_id and chat_id:
            if is_extension:
                # Ошибка продления подписки
                extension_subscription_id = meta.get('extension_subscription_id', 'Неизвестно')
                error_message = (
                    f"{UIStyles.header('Ошибка продления подписки')}\n\n"
                    f"{UIEmojis.ERROR} <b>Платеж не прошел!</b>\n\n"
                    f"<b>Подписка ID:</b> {extension_subscription_id}\n"
                    f"<b>Причина:</b> Платеж был отклонен\n"
                    f"<b>Статус:</b> {status}\n\n"
                    f"{UIStyles.description('Попробуйте продлить заново или обратитесь в поддержку')}"
                )
                
                # Создаем кнопку для открытия мини-приложения
                from ...utils import UIButtons
                webapp_button = UIButtons.create_webapp_button(
                    action='subscriptions'
                )
                
                buttons = []
                if webapp_button:
                    buttons.append([webapp_button])
                
                keyboard = InlineKeyboardMarkup(buttons) if buttons else None
                
                menu_type = MenuTypes.PAYMENT_FAILED
            else:
                # Ошибка обычной покупки
                error_message = (
                    f"{UIStyles.header('Ошибка оплаты')}\n\n"
                    f"{UIEmojis.ERROR} <b>Платеж не прошел!</b>\n\n"
                    f"<b>Причина:</b> Платеж был отклонен\n"
                    f"<b>Статус:</b> {status}\n\n"
                    f"{UIStyles.description('Попробуйте оплатить заново или обратитесь в поддержку')}"
                )
                
                # Создаем кнопку для открытия мини-приложения
                from ...utils import UIButtons
                webapp_button = UIButtons.create_webapp_button(
                    action='subscriptions'
                )
                
                buttons = []
                if webapp_button:
                    buttons.append([webapp_button])
                
                keyboard = InlineKeyboardMarkup(buttons) if buttons else None
                
                menu_type = MenuTypes.PAYMENT_FAILED
            
            await safe_edit_message_with_photo(
                bot_app.bot,
                chat_id=chat_id,
                message_id=message_id,
                text=error_message,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type=menu_type
            )
            logger.info(f"Отправлено сообщение об ошибке пользователю {user_id}")
            
    except (RuntimeError, ValueError, TypeError, KeyError) as e:
        logger.error(f"Ошибка обработки неудачного платежа {payment_id}: {e}")

