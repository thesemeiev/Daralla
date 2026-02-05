"""
Операции админа над пользователями: удаление с отзывом подписки в Remnawave.
"""
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


async def delete_user_full(account_id: int) -> Tuple[int, int]:
    """
    Удаляет пользователя: подписка в Remnawave, платежи и аккаунт локально.
    Возвращает (subscriptions_deleted, payments_deleted).
    """
    from .....db import delete_account, delete_payments_by_account_id
    from .....db.accounts_db import get_remnawave_mapping
    from .....services.remnawave_service import RemnawaveClient, load_remnawave_config, is_remnawave_configured

    remna = await get_remnawave_mapping(account_id)
    subscriptions_deleted = 0

    if remna:
        subscriptions_deleted = 1
        user_uuid = remna.get("remnawave_user_uuid")
        if user_uuid and is_remnawave_configured():
            try:
                client = RemnawaveClient(load_remnawave_config())
                client.delete_user(user_uuid)
            except Exception as e:
                logger.warning("Remnawave delete_user for %s failed (proceeding with local delete): %s", user_uuid, e)

    payments_deleted = await delete_payments_by_account_id(account_id)
    await delete_account(account_id)
    return subscriptions_deleted, payments_deleted
