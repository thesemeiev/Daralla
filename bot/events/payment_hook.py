"""
Хук успешной оплаты: засчитываем оплату приглашённого в рейтинг реферера по активным событиям.
"""
import logging
from bot.events.db.queries import get_active_event_ids_for_referred_user, add_counted_payment

logger = logging.getLogger(__name__)


async def on_payment_success(user_id: str) -> None:
    """
    Вызывается после успешной покупки или продления подписки пользователем user_id (приглашённым).
    Для каждого активного события, в котором user_id участвует как приглашённый,
    добавляется одна запись в event_counted_payments (идемпотентно: один referred+event = один +1).
    """
    if not user_id:
        return
    try:
        event_ids = await get_active_event_ids_for_referred_user(user_id)
        for event_id in event_ids:
            try:
                await add_counted_payment(event_id, user_id)
            except Exception as e:
                logger.warning("add_counted_payment event_id=%s referred=%s: %s", event_id, user_id, e)
    except Exception as e:
        logger.warning("on_payment_success user_id=%s: %s", user_id, e)
