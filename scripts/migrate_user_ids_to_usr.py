#!/usr/bin/env python3
"""
Миграция user_id из форматов tg_/web_ в usr_ (12 hex).
Запуск: python -m scripts.migrate_user_ids_to_usr [--dry-run] [--no-backup]
- Создаёт бэкап data/daralla.db перед миграцией (если не --no-backup)
- Обновляет users, payments, sent_notifications, link_telegram_states, telegram_links,
  event_referrals, event_counted_payments, user_referral_codes
- НЕ трогает subscription_servers.client_email (связь с X-UI)
"""
import argparse
import asyncio
import logging
import os
import shutil
import sys
import time
import uuid

# Добавляем корень проекта в path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiosqlite

from bot.db import DB_PATH
from bot.db.users_db import USER_ID_HEX_LEN

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _generate_new_user_id(existing_ids: set[str]) -> str:
    """Генерирует уникальный usr_xxx."""
    for _ in range(100):
        uid = f"usr_{uuid.uuid4().hex[:USER_ID_HEX_LEN]}"
        if uid not in existing_ids:
            return uid
    raise RuntimeError("Не удалось сгенерировать уникальный user_id")


async def run_migration(dry_run: bool = False, no_backup: bool = False) -> None:
    if dry_run:
        logger.info("=== DRY RUN (изменения не применяются) ===")

    if not os.path.exists(DB_PATH):
        logger.warning("БД не найдена: %s. Сначала запустите приложение для инициализации.", DB_PATH)
        return

    # Бэкап
    if not no_backup and not dry_run:
        backup_path = f"{DB_PATH}.pre_migration_{int(time.time())}"
        shutil.copy2(DB_PATH, backup_path)
        logger.info("Бэкап создан: %s", backup_path)

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = OFF")

        # Проверяем наличие таблицы users
        async with db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'"
        ) as cur:
            if not await cur.fetchone():
                logger.warning("Таблица users не найдена. Сначала инициализируйте БД (запустите приложение).")
                return

        # Получаем всех пользователей с tg_/web_
        async with db.execute(
            "SELECT user_id FROM users WHERE user_id LIKE 'tg_%' OR user_id LIKE 'web_%'"
        ) as cur:
            rows = await cur.fetchall()
        old_users = [r["user_id"] for r in rows]

        if not old_users:
            logger.info("Нет пользователей с tg_/web_ для миграции.")
            return

        # Собираем все текущие user_id для уникальности
        async with db.execute("SELECT user_id FROM users") as cur:
            all_rows = await cur.fetchall()
        existing_ids = {r["user_id"] for r in all_rows}

        # План миграции: old -> new
        migration_plan: list[tuple[str, str]] = []
        for old_id in old_users:
            new_id = _generate_new_user_id(existing_ids)
            migration_plan.append((old_id, new_id))
            existing_ids.add(new_id)

        logger.info("Запланировано миграций: %d", len(migration_plan))
        for old_id, new_id in migration_plan[:5]:
            logger.info("  %s -> %s", old_id, new_id)
        if len(migration_plan) > 5:
            logger.info("  ... и ещё %d", len(migration_plan) - 5)

        if dry_run:
            logger.info("DRY RUN: миграция не выполнена.")
            return

        try:
            await db.execute("BEGIN TRANSACTION")

            for old_id, new_id in migration_plan:
                # Обновляем все таблицы
                await db.execute(
                    "UPDATE users SET user_id = ? WHERE user_id = ?",
                    (new_id, old_id),
                )
                await db.execute(
                    "UPDATE payments SET user_id = ? WHERE user_id = ?",
                    (new_id, old_id),
                )
                await db.execute(
                    "UPDATE sent_notifications SET user_id = ? WHERE user_id = ?",
                    (new_id, old_id),
                )
                await db.execute(
                    "UPDATE link_telegram_states SET user_id = ? WHERE user_id = ?",
                    (new_id, old_id),
                )
                await db.execute(
                    "UPDATE telegram_links SET user_id = ? WHERE user_id = ?",
                    (new_id, old_id),
                )

                async with db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='event_referrals'"
                ) as cur:
                    if await cur.fetchone():
                        await db.execute(
                            "UPDATE event_referrals SET referrer_user_id = ? WHERE referrer_user_id = ?",
                            (new_id, old_id),
                        )
                        await db.execute(
                            "UPDATE event_referrals SET referred_user_id = ? WHERE referred_user_id = ?",
                            (new_id, old_id),
                        )
                async with db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='event_counted_payments'"
                ) as cur:
                    if await cur.fetchone():
                        await db.execute(
                            "UPDATE event_counted_payments SET referred_user_id = ? WHERE referred_user_id = ?",
                            (new_id, old_id),
                        )
                async with db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='user_referral_codes'"
                ) as cur:
                    if await cur.fetchone():
                        await db.execute(
                            "UPDATE user_referral_codes SET user_id = ? WHERE user_id = ?",
                            (new_id, old_id),
                        )

            await db.commit()
            logger.info("Миграция успешно завершена. Обновлено пользователей: %d", len(migration_plan))

        except Exception as e:
            await db.rollback()
            logger.error("Ошибка миграции: %s", e, exc_info=True)
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Миграция user_id tg_/web_ -> usr_")
    parser.add_argument("--dry-run", action="store_true", help="Показать план без применения")
    parser.add_argument("--no-backup", action="store_true", help="Не создавать бэкап")
    args = parser.parse_args()

    asyncio.run(run_migration(dry_run=args.dry_run, no_backup=args.no_backup))


if __name__ == "__main__":
    main()
