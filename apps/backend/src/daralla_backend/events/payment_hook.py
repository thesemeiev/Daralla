"""
Хук успешной оплаты: засчитываем оплату с кодом в рейтинг реферера по активным событиям.
"""
import logging
from daralla_backend.events.db.queries import list_events_active, add_counted_payment

logger = logging.getLogger(__name__)


async def on_payment_success(user_id: str, payment_id: str, meta: dict) -> None:
    """
    Вызывается после успешной покупки или продления подписки.
    Если в meta есть referrer_user_id (код введён при покупке), для каждого активного
    события добавляется запись в event_counted_payments (каждая покупка = один балл).
    """
    referrer_user_id = (meta or {}).get("referrer_user_id")
    if not referrer_user_id or not payment_id:
        return
    try:
        active_events = await list_events_active()
        for ev in active_events:
            event_id = ev.get("id")
            if event_id is None:
                continue
            try:
                await add_counted_payment(event_id, referrer_user_id, payment_id)
            except Exception as e:
                logger.warning(
                    "add_counted_payment event_id=%s referrer=%s payment_id=%s: %s",
                    event_id,
                    referrer_user_id,
                    payment_id,
                    e,
                )
    except Exception as e:
        logger.warning("on_payment_success user_id=%s payment_id=%s: %s", user_id, payment_id, e)
