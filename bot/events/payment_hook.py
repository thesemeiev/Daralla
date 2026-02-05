"""
Хук успешной оплаты: засчитываем оплату приглашённого в рейтинг реферера по активным событиям.
"""
import logging
from bot.events.db.queries import get_active_event_ids_for_referred_user, add_counted_payment

logger = logging.getLogger(__name__)


async def on_payment_success(account_id: str) -> None:
    """
    Вызывается после успешной покупки или продления подписки пользователем (приглашённым).
    Для каждого активного события, в котором account_id участвует как приглашённый,
    добавляется одна запись в event_counted_payments (идемпотентно: один referred+event = один +1).
    """
    if not account_id:
        return
    try:
        event_ids = await get_active_event_ids_for_referred_user(account_id)
        for event_id in event_ids:
            try:
                await add_counted_payment(event_id, account_id)
            except Exception as e:
                logger.warning("add_counted_payment event_id=%s referred=%s: %s", event_id, account_id, e)
    except Exception as e:
        logger.warning("on_payment_success account_id=%s: %s", account_id, e)
