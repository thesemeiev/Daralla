"""
Добавляет столбцы repeat_every_hours и max_repeats в notification_rules.
Ранее эта миграция выполнялась ad-hoc внутри init_notifications_db().
"""
import aiosqlite

DESCRIPTION = "notification_rules: repeat_every_hours, max_repeats"


async def up(db: aiosqlite.Connection) -> None:
    for col, default in [("repeat_every_hours", 0), ("max_repeats", 1)]:
        try:
            await db.execute(
                f"ALTER TABLE notification_rules ADD COLUMN {col} INTEGER DEFAULT {default}"
            )
        except Exception:
            pass
