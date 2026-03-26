"""
ETL cutover script for RemnaWave-oriented bindings.

Usage:
  python scripts/migrate_remnawave_cutover.py --dry-run
  python scripts/migrate_remnawave_cutover.py --apply
  python scripts/migrate_remnawave_cutover.py --rollback --backup-file data/daralla.db.cutover.bak
"""
from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path


def _backup_db(db_path: Path) -> Path:
    backup_path = db_path.with_suffix(db_path.suffix + ".cutover.bak")
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(backup_path)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    return backup_path


def rollback(db_path: Path, backup_path: Path) -> None:
    if not backup_path.exists():
        raise SystemExit(f"Backup file not found: {backup_path}")
    src = sqlite3.connect(backup_path)
    dst = sqlite3.connect(db_path)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    print(f"ROLLBACK: restored {db_path} from {backup_path}")


def run(db_path: Path, apply: bool) -> None:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS remnawave_bindings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subscription_id INTEGER NOT NULL UNIQUE,
            user_id TEXT NOT NULL,
            panel_user_id TEXT NOT NULL,
            subscription_url TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """
    )

    rows = cur.execute(
        """
        SELECT s.id, u.user_id, s.subscription_token
        FROM subscriptions s
        JOIN users u ON u.id = s.subscriber_id
        WHERE s.status != 'deleted'
        """
    ).fetchall()

    now = int(time.time())
    inserted = 0
    for sub_id, user_id, token in rows:
        panel_user_id = f"imported-{sub_id}"
        subscription_url = f"/sub/{token}"
        if apply:
            cur.execute(
                """
                INSERT INTO remnawave_bindings
                    (subscription_id, user_id, panel_user_id, subscription_url, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(subscription_id) DO NOTHING
                """,
                (sub_id, user_id, panel_user_id, subscription_url, now, now),
            )
        inserted += 1

    if apply:
        backup_path = _backup_db(db_path)
        print(f"BACKUP: {backup_path}")
        conn.commit()
    conn.close()
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"{mode}: scanned={len(rows)} prepared={inserted}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/daralla.db")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--backup-file", default="")
    args = parser.parse_args()
    selected = int(bool(args.dry_run)) + int(bool(args.apply)) + int(bool(args.rollback))
    if selected != 1:
        raise SystemExit("Choose exactly one: --dry-run, --apply or --rollback")
    if args.rollback:
        if not args.backup_file:
            raise SystemExit("--backup-file is required with --rollback")
        rollback(Path(args.db), Path(args.backup_file))
        raise SystemExit(0)
    run(Path(args.db), apply=args.apply)
