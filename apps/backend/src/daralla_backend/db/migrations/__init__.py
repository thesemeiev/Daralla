"""
Система миграций БД.

Каждая миграция — модуль с async def up(db) и описанием DESCRIPTION.
Файлы именуются NNN_name.py и выполняются по порядку номеров.
Версии хранятся в таблице schema_version.
"""
import importlib
import logging
import os
import re

import aiosqlite

from .. import DB_PATH

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = os.path.dirname(os.path.abspath(__file__))
_MIGRATION_RE = re.compile(r"^(\d{3})_\w+\.py$")


async def _ensure_version_table(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))
        )
    """)
    await db.commit()


async def _get_current_version(db: aiosqlite.Connection) -> int:
    async with db.execute("SELECT MAX(version) FROM schema_version") as cur:
        row = await cur.fetchone()
        return row[0] or 0


def _discover_migrations() -> list[tuple[int, str, str]]:
    """Возвращает [(version, module_name, filename), ...] отсортированные по version."""
    results = []
    for fname in os.listdir(MIGRATIONS_DIR):
        m = _MIGRATION_RE.match(fname)
        if m:
            version = int(m.group(1))
            module_name = fname[:-3]
            results.append((version, module_name, fname))
    results.sort(key=lambda x: x[0])
    return results


async def run_migrations() -> int:
    """
    Запускает все непримененные миграции по порядку.
    Возвращает количество примененных миграций.
    """
    applied = 0
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        # Ожидание при конкурентных writer/readers (админка + фоновые задачи)
        await db.execute("PRAGMA busy_timeout=15000")
        await _ensure_version_table(db)
        current = await _get_current_version(db)
        migrations = _discover_migrations()

        for version, module_name, fname in migrations:
            if version <= current:
                continue

            logger.info("Применяю миграцию %03d (%s)...", version, module_name)
            mod = importlib.import_module(f".{module_name}", package=__name__)

            await mod.up(db)

            await db.execute(
                "INSERT INTO schema_version (version, name) VALUES (?, ?)",
                (version, module_name),
            )
            await db.commit()
            applied += 1
            desc = getattr(mod, "DESCRIPTION", "")
            logger.info("Миграция %03d применена: %s", version, desc)

    if applied:
        logger.info("Всего применено миграций: %d", applied)
    else:
        logger.info("БД актуальна, новых миграций нет")
    return applied
