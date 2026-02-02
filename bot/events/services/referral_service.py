"""
Сервис рефералов: запись визита по реферальной ссылке (правило «первый ref выигрывает»).
"""
import logging
from bot.events.db.queries import record_referral

logger = logging.getLogger(__name__)


async def record_visit(referrer_user_id: str, referred_user_id: str, event_id: int) -> bool:
    """
    Записывает визит по реферальной ссылке в рамках события. Не перезаписывает реферера, если
    для приглашённого уже есть запись (первый ref выигрывает). Возвращает True если запись добавлена.
    event_id обязателен — глобальные рефералы не поддерживаются.
    """
    if not referrer_user_id or not referred_user_id or event_id is None:
        return False
    if referrer_user_id == referred_user_id:
        return False
    try:
        return await record_referral(referrer_user_id, referred_user_id, event_id)
    except Exception as e:
        logger.warning("record_visit failed: %s", e)
        return False
