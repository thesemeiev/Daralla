"""
Модуль фоновой отправки бекапов базы данных администратору.
"""
import asyncio
import logging
import os
from pathlib import Path
import gzip
import shutil
from datetime import datetime

logger = logging.getLogger(__name__)


async def _send_db_file(bot, admin_id: int, db_path: Path):
    if not db_path.exists():
        logger.warning("DB file for backup not found: %s", db_path)
        return
    try:
        # Сжимаем в tmp gzip перед отправкой, чтобы уменьшить размер
        gz_path = db_path.with_suffix(db_path.suffix + ".gz")
        try:
            with db_path.open('rb') as f_in, gzip.open(gz_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        except Exception:
            logger.exception("Ошибка при сжатии бекапа, отправлю оригинал")
            gz_path = db_path

        filename = f"{db_path.name}.{datetime.utcnow().strftime('%Y%m%d%H%M')}.gz" if gz_path != db_path else db_path.name
        with gz_path.open('rb') as f:
            await bot.send_document(chat_id=admin_id, document=f, filename=filename)

        # Удаляем временный файл если он был создан
        if gz_path != db_path and gz_path.exists():
            try:
                gz_path.unlink()
            except Exception:
                logger.debug("Не удалось удалить временный файл %s", gz_path)

        logger.info("DB backup sent to admin %s: %s", admin_id, db_path)
    except Exception:
        logger.exception("Failed to send DB backup to admin %s", admin_id)


async def _backup_loop(bot, admin_id: int, db_path: Path, interval: int):
    # Небольшая задержка после старта
    await asyncio.sleep(10)
    while True:
        try:
            await _send_db_file(bot, admin_id, db_path)
        except Exception:
            logger.exception("Ошибка в цикле бекапа")
        await asyncio.sleep(interval)


def _resolve_admin_id(env_admin: str | None) -> int | None:
    if not env_admin:
        return None
    try:
        return int(env_admin.split(',')[0].strip())
    except Exception:
        logger.exception("Invalid ADMIN_ID: %s", env_admin)
        return None


def install_backup_task(app_or_bot, interval_seconds: int = 2 * 60 * 60, db_path: str | None = None, admin_id: str | None = None):
    """
    Устанавливает фоновый таск отправки бекапа.
    - `app_or_bot` может быть `telegram.ext.Application` или `telegram.Bot`.
    - Если передан `Application`, используем `app_or_bot.bot`.
    - `admin_id` можно передать явно, иначе берём из env `ADMIN_ID`.
    """
    env_admin = admin_id or os.getenv('ADMIN_ID')
    admin = _resolve_admin_id(env_admin)
    if not admin:
        logger.warning('ADMIN_ID not set or invalid — backup task not installed')
        return

    # Определяем путь к БД
    path = None
    if db_path:
        path = Path(db_path)
    else:
        # Обычное место — data/daralla.db
        repo_root = Path(__file__).resolve().parents[2]
        candidate = repo_root / 'data' / 'daralla.db'
        if candidate.exists():
            path = candidate
        else:
            # fallback: первый .db в папке data
            data_dir = repo_root / 'data'
            if data_dir.exists():
                files = list(data_dir.glob('*.db'))
                path = files[0] if files else candidate
            else:
                path = candidate

    # Получаем объект bot
    bot = getattr(app_or_bot, 'bot', app_or_bot)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_backup_loop(bot, admin, path, interval_seconds))
        logger.info('Backup task installed (interval=%s sec) -> admin=%s db=%s', interval_seconds, admin, path)
    except RuntimeError:
        # Нет запущенного event loop — запускаем в отдельном демоне
        def _starter():
            asyncio.run(_backup_loop(bot, admin, path, interval_seconds))
        import threading
        t = threading.Thread(target=_starter, daemon=True)
        t.start()
        logger.info('Backup thread started (no running event loop)')
