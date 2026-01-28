"""
Миграция данных для таблиц telegram_links и known_telegram_ids.

Запускать один раз после деплоя новой схемы.
"""

import asyncio
import aiosqlite
import logging
from .. import DB_PATH

logger = logging.getLogger(__name__)


async def migrate_telegram_links():
    """
    Мигрирует существующие связи Telegram ↔ аккаунты в новые таблицы:
    - telegram_links
    - known_telegram_ids

    Шаги:
    1. Веб-привязки: users.telegram_id -> telegram_links(telegram_id, user_id, linked_at)
    2. TG-first аккаунты: числовой users.user_id -> telegram_links(telegram_id=user_id, user_id=user_id)
    3. known_telegram_ids: все telegram_id из telegram_links + все числовые user_id
    4. (Опционально) Чистка orphaned_* без данных можно сделать отдельным скриптом.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # 1. Мигрируем веб-привязки (users.telegram_id)
        logger.info("Миграция веб-привязок в telegram_links...")
        await db.execute(
            """
            INSERT OR IGNORE INTO telegram_links (telegram_id, user_id, linked_at)
            SELECT telegram_id, user_id, last_seen
            FROM users
            WHERE telegram_id IS NOT NULL
            """
        )

        # 2. Мигрируем TG-first аккаунты (user_id - числовая строка, is_web = 0)
        logger.info("Миграция TG-first аккаунтов в telegram_links...")
        await db.execute(
            """
            INSERT OR IGNORE INTO telegram_links (telegram_id, user_id, linked_at)
            SELECT user_id AS telegram_id, user_id, first_seen
            FROM users
            WHERE user_id GLOB '[0-9]*' AND (is_web IS NULL OR is_web = 0)
            """
        )

        # 3. Заполняем known_telegram_ids
        logger.info("Заполнение known_telegram_ids...")
        await db.execute(
            """
            INSERT OR IGNORE INTO known_telegram_ids (telegram_id, first_seen_at)
            SELECT telegram_id, linked_at
            FROM telegram_links
            """
        )

        await db.execute(
            """
            INSERT OR IGNORE INTO known_telegram_ids (telegram_id, first_seen_at)
            SELECT user_id AS telegram_id, first_seen
            FROM users
            WHERE user_id GLOB '[0-9]*'
            """
        )

        await db.commit()
        logger.info("Миграция telegram_links/known_telegram_ids завершена.")


if __name__ == "__main__":
    asyncio.run(migrate_telegram_links())

