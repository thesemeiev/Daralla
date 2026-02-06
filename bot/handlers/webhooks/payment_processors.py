"""
Обработчики платежей из webhook'ов YooKassa
"""
import logging
import json
import datetime
from typing import Optional
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

from ...db import get_payment_by_id, update_payment_status, update_payment_activation, update_payment_meta
from ...db.accounts_db import get_telegram_id_for_account
from ...utils import (
    UIEmojis, UIStyles, UIMessages, UIButtons,
    safe_edit_message_with_photo, safe_send_message_with_photo
)
from ...navigation import MenuTypes

logger = logging.getLogger(__name__)


# ============= HELPER ФУНКЦИИ =============

async def _send_payment_message(bot_app, chat_id: int, message_id: int, text: str, 
                                menu_type: str, action: str = 'subscriptions', 
                                short_uuid: Optional[str] = None) -> bool:
    """Единая функция для отправки сообщений о платежах."""
    try:
        webapp_button = UIButtons.create_webapp_button(action=action, params=short_uuid)
        buttons = [[webapp_button]] if webapp_button else []
        keyboard = InlineKeyboardMarkup(buttons) if buttons else None
        
        if message_id:
            await safe_edit_message_with_photo(
                bot_app.bot,
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type=menu_type,
            )
        else:
            await safe_send_message_with_photo(
                bot_app.bot,
                chat_id=chat_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML",
                menu_type=menu_type,
            )
        return True
    except Exception as e:
        logger.error("Ошибка отправки сообщения о платеже chat_id=%s: %s", chat_id, e)
        return False


def _build_success_message(period_text: str, expiry_str: str, device_limit: int, 
                          subscription_url: str = "", is_extension: bool = False) -> str:
    """Строит сообщение об успешной оплате."""
    if is_extension:
        message = (
            f"{UIStyles.header('Подписка продлена!')}\n\n"
            f"{UIEmojis.SUCCESS} <b>Ваша подписка успешно продлена</b>\n\n"
            f"<b>Период:</b> {period_text}\n"
            f"<b>Новое окончание:</b> {expiry_str}\n\n"
            f"{UIStyles.description('Подписка активна и готова к использованию.')}"
        )
    else:
        message = (
            f"{UIStyles.header('Подписка активирована!')}\n\n"
            f"{UIEmojis.SUCCESS} <b>Ваша подписка успешно создана</b>\n\n"
            f"<b>Период:</b> {period_text}\n"
            f"<b>Окончание:</b> {expiry_str}\n"
            f"<b>Устройств:</b> {device_limit}\n\n"
        )
        if subscription_url:
            message += f"{UIStyles.header('Ссылка на подписку:')}\n<code>{subscription_url}</code>\n\n"
        message += f"{UIStyles.description('Используйте эту ссылку для импорта в VPN-клиент.')}"
    
    return message


def _build_error_message(status: str, is_extension: bool = False, 
                        extension_subscription_id: Optional[str] = None) -> str:
    """Строит сообщение об ошибке платежа."""
    if is_extension:
        return (
            f"{UIStyles.header('Ошибка продления подписки')}\n\n"
            f"{UIEmojis.ERROR} <b>Платеж не прошел!</b>\n\n"
            f"<b>Подписка ID:</b> {extension_subscription_id or 'Неизвестно'}\n"
            f"<b>Причина:</b> Платеж был отклонен\n"
            f"<b>Статус:</b> {status}\n\n"
            f"{UIStyles.description('Попробуйте продлить заново или обратитесь в поддержку')}"
        )
    else:
        return (
            f"{UIStyles.header('Ошибка оплаты')}\n\n"
            f"{UIEmojis.ERROR} <b>Платеж не прошел!</b>\n\n"
            f"<b>Причина:</b> Платеж был отклонен/отменен\n"
            f"<b>Статус:</b> {status}\n\n"
            f"{UIStyles.description('Попробуйте оплатить заново или обратитесь в поддержку')}"
        )


async def process_payment_webhook(bot_app, payment_id, status):
    """Обрабатывает платеж из webhook'а"""
    try:
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
        
        account_id_str = payment_info.get('account_id') or ''
        meta = payment_info['meta'] if isinstance(payment_info['meta'], dict) else json.loads(payment_info['meta'])
        
        logger.info(f"Обработка webhook платежа: payment_id={payment_id}, account_id={account_id_str}, status={status}, current_status={current_status}, activated={is_activated}")
        
        # Обрабатываем платеж в зависимости от статуса
        if status == 'succeeded':
            await process_successful_payment(bot_app, payment_id, account_id_str, meta)
        elif status in ['canceled', 'refunded']:
            await process_canceled_payment(bot_app, payment_id, account_id_str, meta, status)
        elif status not in ['pending']:
            await process_failed_payment(bot_app, payment_id, account_id_str, meta, status)
        
    except Exception as e:
        logger.error(f"Ошибка обработки webhook платежа {payment_id}: {e}")


async def _get_chat_id_for_account(account_id_str: str):
    """Для уведомлений: account_id_str = str(account_id), берём chat_id по identity."""
    if isinstance(account_id_str, str) and account_id_str.isdigit():
        tid = await get_telegram_id_for_account(int(account_id_str))
        return int(tid) if tid else None
    return None


async def process_successful_payment(bot_app, payment_id, account_id_str, meta):
    """Обрабатывает успешный платеж. account_id_str = str(account_id)."""
    try:
        from ...services.remnawave_service import is_remnawave_configured
        message_id = meta.get('message_id')
        if not isinstance(account_id_str, str) or not account_id_str.isdigit() or not is_remnawave_configured():
            logger.warning("Платеж %s: ожидается account_id и Remnawave", payment_id)
            await update_payment_status(payment_id, 'failed')
            return
        account_id = int(account_id_str)
        await process_successful_payment_remnawave(bot_app, payment_id, account_id, meta, message_id)
    except Exception as e:
        logger.error(f"Ошибка обработки успешного платежа {payment_id}: {e}")


async def process_successful_payment_remnawave(bot_app, payment_id, account_id, meta, message_id):
    """
    Успешная оплата: активация/продление в Remnawave через subscription_service,
    обновление платежа в БД и уведомление в Telegram.
    """
    from ...services.subscription_service import activate_subscription_after_payment

    period = meta.get("type", "month")
    device_limit = int(meta.get("device_limit", 1))
    actual_period = period.replace("extend_sub_", "", 1).replace("extend_", "", 1) if period.startswith("extend_") else period
    days = 90 if actual_period == "3month" else 30
    is_extension = period.startswith("extend_")

    success, short_uuid, new_expires_at, _err = await activate_subscription_after_payment(
        account_id, days=days, device_limit=device_limit, is_extension=is_extension
    )
    
    if not success or new_expires_at is None:
        await update_payment_status(payment_id, "failed")
        return

    await update_payment_status(payment_id, "succeeded")
    await update_payment_activation(payment_id, True)

    try:
        from bot.events import EVENTS_MODULE_ENABLED, on_payment_success as events_on_payment_success
        if EVENTS_MODULE_ENABLED:
            await events_on_payment_success(str(account_id))
    except Exception as events_e:
        logger.debug("events.on_payment_success (remnawave): %s", events_e)

    chat_id = await get_telegram_id_for_account(account_id)
    if not chat_id:
        logger.warning("No Telegram ID for account %d, skipping notification", account_id)
        return
    
    expiry_str = datetime.datetime.fromtimestamp(new_expires_at).strftime("%d.%m.%Y %H:%M")
    period_text = "3 месяца" if actual_period == "3month" else "1 месяц"

    from ...config import SUBSCRIPTION_URL, WEBHOOK_URL
    base_url = (SUBSCRIPTION_URL or WEBHOOK_URL or "").rstrip("/")
    subscription_url = f"{base_url}/sub/{short_uuid}" if (base_url and "://" in base_url and short_uuid) else ""

    # Сохраняем в meta для отображения в Web App после возврата из ЮKassa
    await update_payment_meta(payment_id, {
        "subscription_url": subscription_url or "",
        "short_uuid": short_uuid or "",
        "expires_at": new_expires_at,
        "period": actual_period,
        "device_limit": device_limit,
    })

    success_message = _build_success_message(
        period_text=period_text,
        expiry_str=expiry_str,
        device_limit=device_limit,
        subscription_url=subscription_url,
        is_extension=is_extension
    )

    await _send_payment_message(
        bot_app=bot_app,
        chat_id=int(chat_id),
        message_id=message_id,
        text=success_message,
        menu_type=MenuTypes.PAYMENT_SUCCESS,
        action='subscription' if is_extension else 'subscriptions',
        short_uuid=short_uuid if is_extension else None
    )


async def process_canceled_payment(bot_app, payment_id, user_id, meta, status):
    """Обрабатывает отмененный платеж"""
    try:
        await update_payment_status(payment_id, 'failed')
        await update_payment_activation(payment_id, False)
        
        message_id = meta.get('message_id')
        chat_id = await _get_chat_id_for_account(user_id)
        
        if message_id and chat_id:
            error_message = _build_error_message(status=status, is_extension=False)
            await _send_payment_message(
                bot_app=bot_app,
                chat_id=chat_id,
                message_id=message_id,
                text=error_message,
                menu_type=MenuTypes.PAYMENT_FAILED,
                action='subscriptions'
            )
            logger.info("Отправлено сообщение об ошибке оплаты пользователю %s", user_id)
                    
    except Exception as e:
        logger.error(f"Ошибка обработки отмененного платежа {payment_id}: {e}")


async def process_failed_payment(bot_app, payment_id, account_id_str, meta, status):
    """Обрабатывает неудачный платеж"""
    try:
        await update_payment_status(payment_id, 'failed')
        await update_payment_activation(payment_id, False)
        
        chat_id = await _get_chat_id_for_account(account_id_str)
        period = meta.get('type', 'month')
        is_extension = period.startswith('extend_')
        
        message_id = meta.get('message_id')
        if message_id and chat_id:
            extension_subscription_id = meta.get('extension_subscription_id') if is_extension else None
            error_message = _build_error_message(
                status=status,
                is_extension=is_extension,
                extension_subscription_id=extension_subscription_id
            )
            
            await _send_payment_message(
                bot_app=bot_app,
                chat_id=chat_id,
                message_id=message_id,
                text=error_message,
                menu_type=MenuTypes.PAYMENT_FAILED,
                action='subscriptions'
            )
            logger.info(f"Отправлено сообщение об ошибке пользователю {account_id_str}")
            
    except Exception as e:
        logger.error(f"Ошибка обработки неудачного платежа {payment_id}: {e}")

