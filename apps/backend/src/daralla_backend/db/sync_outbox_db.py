"""
DB helpers for sync outbox jobs (БД -> 3x-ui).
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Iterable

import aiosqlite

from . import DB_PATH

_LIVE_STATUSES = ("pending", "retry")
_SCHEMA_READY = False
_SCHEMA_LOCK = asyncio.Lock()


def _now_ts() -> int:
    return int(time.time())


async def ensure_sync_outbox_schema() -> None:
    """
    Defensive self-heal for environments where schema_version is ahead,
    but sync_outbox table is missing (e.g. old DB restored with stale version rows).
    """
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return
    async with _SCHEMA_LOCK:
        if _SCHEMA_READY:
            return
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    subscription_id INTEGER NOT NULL,
                    server_name TEXT NOT NULL,
                    client_email TEXT NOT NULL,
                    op TEXT NOT NULL DEFAULT 'ensure_client',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    desired_revision INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_run_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
                    last_error TEXT,
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
                    updated_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
                    done_at INTEGER,
                    FOREIGN KEY (subscription_id) REFERENCES subscriptions(id)
                )
                """
            )
            await db.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_sync_outbox_unique_job
                ON sync_outbox(subscription_id, server_name, client_email, op, desired_revision)
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sync_outbox_status_run
                ON sync_outbox(status, next_run_at, id)
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sync_outbox_subscription
                ON sync_outbox(subscription_id, id)
                """
            )
            await db.commit()
        _SCHEMA_READY = True


async def enqueue_sync_job(
    *,
    subscription_id: int,
    server_name: str,
    client_email: str,
    op: str = "ensure_client",
    desired_revision: int = 0,
    payload: dict | None = None,
    next_run_at: int | None = None,
) -> bool:
    await ensure_sync_outbox_schema()
    now = _now_ts()
    run_at = int(next_run_at) if next_run_at is not None else now
    payload_json = json.dumps(payload or {}, ensure_ascii=False)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            INSERT OR IGNORE INTO sync_outbox
            (subscription_id, server_name, client_email, op, payload_json, desired_revision, status, attempts, next_run_at, last_error, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', 0, ?, NULL, ?, ?)
            """,
            (
                int(subscription_id),
                str(server_name),
                str(client_email),
                str(op),
                payload_json,
                int(desired_revision),
                run_at,
                now,
                now,
            ),
        )
        await db.commit()
        return (cur.rowcount or 0) > 0


async def enqueue_sync_jobs_bulk(jobs: Iterable[dict]) -> int:
    inserted = 0
    for job in jobs:
        ok = await enqueue_sync_job(
            subscription_id=int(job["subscription_id"]),
            server_name=str(job["server_name"]),
            client_email=str(job["client_email"]),
            op=str(job.get("op", "ensure_client")),
            desired_revision=int(job.get("desired_revision", 0)),
            payload=job.get("payload") if isinstance(job.get("payload"), dict) else None,
            next_run_at=job.get("next_run_at"),
        )
        if ok:
            inserted += 1
    return inserted


async def claim_due_jobs(limit: int = 50) -> list[dict]:
    await ensure_sync_outbox_schema()
    now = _now_ts()
    lim = max(1, min(int(limit), 500))
    ids: list[int] = []
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA busy_timeout=15000")
        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(
            """
            SELECT id FROM sync_outbox
            WHERE status IN ('pending', 'retry')
              AND next_run_at <= ?
            ORDER BY next_run_at ASC, id ASC
            LIMIT ?
            """,
            (now, lim),
        ) as cur:
            rows = await cur.fetchall()
            ids = [int(r["id"]) for r in rows]
        if not ids:
            await db.execute("COMMIT")
            return []
        placeholders = ",".join("?" for _ in ids)
        await db.execute(
            f"""
            UPDATE sync_outbox
            SET status = 'processing',
                attempts = attempts + 1,
                updated_at = ?
            WHERE id IN ({placeholders})
            """,
            (now, *ids),
        )
        await db.execute("COMMIT")

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        placeholders = ",".join("?" for _ in ids)
        async with db.execute(
            f"""
            SELECT * FROM sync_outbox
            WHERE id IN ({placeholders})
            ORDER BY id ASC
            """,
            (*ids,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def mark_job_done(job_id: int) -> None:
    await ensure_sync_outbox_schema()
    now = _now_ts()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE sync_outbox
            SET status = 'done',
                last_error = NULL,
                done_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (now, now, int(job_id)),
        )
        await db.commit()


async def mark_job_retry(job_id: int, *, error_text: str, delay_sec: int) -> None:
    await ensure_sync_outbox_schema()
    now = _now_ts()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE sync_outbox
            SET status = 'retry',
                next_run_at = ?,
                last_error = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (now + max(1, int(delay_sec)), str(error_text)[:2000], now, int(job_id)),
        )
        await db.commit()


async def mark_job_dead(job_id: int, *, error_text: str) -> None:
    await ensure_sync_outbox_schema()
    now = _now_ts()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE sync_outbox
            SET status = 'dead',
                last_error = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (str(error_text)[:2000], now, int(job_id)),
        )
        await db.commit()


async def get_sync_outbox_stats() -> dict:
    await ensure_sync_outbox_schema()
    now = _now_ts()
    out = {
        "pending": 0,
        "retry": 0,
        "processing": 0,
        "done": 0,
        "dead": 0,
        "due_now": 0,
        "oldest_due_age_sec": 0,
    }
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT status, COUNT(*) AS c
            FROM sync_outbox
            GROUP BY status
            """
        ) as cur:
            for row in await cur.fetchall():
                s = str(row["status"] or "")
                if s in out:
                    out[s] = int(row["c"] or 0)
        async with db.execute(
            """
            SELECT COUNT(*) AS c
            FROM sync_outbox
            WHERE status IN ('pending', 'retry') AND next_run_at <= ?
            """,
            (now,),
        ) as cur:
            row = await cur.fetchone()
            out["due_now"] = int((row["c"] if row else 0) or 0)
        async with db.execute(
            """
            SELECT MIN(next_run_at) AS min_due
            FROM sync_outbox
            WHERE status IN ('pending', 'retry')
            """
        ) as cur:
            row = await cur.fetchone()
            min_due = int(row["min_due"]) if row and row["min_due"] is not None else None
            if min_due is not None:
                out["oldest_due_age_sec"] = max(0, now - min_due)
    return out


async def list_sync_outbox_jobs(status: str | None = None, limit: int = 100) -> list[dict]:
    await ensure_sync_outbox_schema()
    lim = max(1, min(int(limit), 500))
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if status:
            async with db.execute(
                """
                SELECT * FROM sync_outbox
                WHERE status = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (str(status), lim),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]
        async with db.execute(
            """
            SELECT * FROM sync_outbox
            ORDER BY id DESC
            LIMIT ?
            """,
            (lim,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def retry_dead_jobs(limit: int = 100) -> int:
    await ensure_sync_outbox_schema()
    now = _now_ts()
    lim = max(1, min(int(limit), 1000))
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT id FROM sync_outbox
            WHERE status = 'dead'
            ORDER BY id ASC
            LIMIT ?
            """,
            (lim,),
        ) as cur:
            ids = [int(r[0]) for r in await cur.fetchall()]
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        await db.execute(
            f"""
            UPDATE sync_outbox
            SET status = 'retry',
                next_run_at = ?,
                last_error = NULL,
                updated_at = ?
            WHERE id IN ({placeholders})
            """,
            (now, now, *ids),
        )
        await db.commit()
        return len(ids)
