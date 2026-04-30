"""High-level helpers for enqueueing and applying sync outbox jobs."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from daralla_backend.db import (
    claim_due_jobs,
    enqueue_sync_jobs_bulk,
    get_subscription_by_id_only,
    get_subscriptions_to_sync,
    get_subscription_servers,
    get_sync_outbox_stats,
    list_sync_outbox_jobs,
    mark_job_dead,
    mark_job_done,
    mark_job_retry,
    retry_dead_jobs,
)
from daralla_backend.services.admin_subscriptions_service import get_user_id_from_subscription_id

logger = logging.getLogger(__name__)


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() not in ("0", "false", "no", "off")


def _int_env(name: str, default: int, min_val: int = 1, max_val: int = 10_000) -> int:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        v = int(raw)
    except ValueError:
        return default
    return max(min_val, min(max_val, v))


def outbox_write_enabled() -> bool:
    return _bool_env("DARALLA_SYNC_OUTBOX_WRITE_ENABLED", True)


def outbox_worker_enabled() -> bool:
    return _bool_env("DARALLA_SYNC_OUTBOX_WORKER_ENABLED", True)


async def enqueue_subscription_sync_jobs(
    subscription_id: int,
    *,
    reason: str = "",
    server_names: list[str] | None = None,
) -> int:
    """Put ensure_client jobs for subscription's servers (dedup by unique index)."""
    if not outbox_write_enabled():
        return 0
    sub = await get_subscription_by_id_only(int(subscription_id))
    if not sub:
        return 0
    status = str(sub.get("status") or "")
    op = "delete_client" if status == "deleted" else "ensure_client"
    revision = int(sub.get("sync_revision") or 0)
    servers = await get_subscription_servers(int(subscription_id))
    if server_names:
        allow = {str(s) for s in server_names}
        servers = [s for s in servers if str(s.get("server_name")) in allow]
    jobs = []
    for s in servers:
        jobs.append(
            {
                "subscription_id": int(subscription_id),
                "server_name": str(s["server_name"]),
                "client_email": str(s["client_email"]),
                "op": op,
                "desired_revision": revision,
                "payload": {"reason": reason or "unspecified"},
            }
        )
    if not jobs:
        return 0
    inserted = await enqueue_sync_jobs_bulk(jobs)
    if inserted:
        logger.info(
            "Outbox enqueue: sub=%s jobs=%s op=%s revision=%s reason=%s",
            subscription_id,
            inserted,
            op,
            revision,
            reason,
        )
    return inserted


async def enqueue_group_sync_jobs(group_id: int, *, reason: str = "") -> int:
    if not outbox_write_enabled():
        return 0
    subs = await get_subscriptions_to_sync()
    total = 0
    for sub in subs:
        if int(sub.get("group_id") or 0) != int(group_id):
            continue
        total += await enqueue_subscription_sync_jobs(
            int(sub["id"]),
            reason=reason or "group_change",
        )
    return total


def _backoff_delay_sec(attempts: int) -> int:
    # 5s, 10s, 20s, ... cap 10min
    a = max(1, int(attempts))
    return min(600, 5 * (2 ** (a - 1)))


async def _apply_outbox_job(job: dict, *, subscription_manager) -> tuple[bool, str | None, bool]:
    """
    Returns:
    - success
    - error text or None
    - stale (job revision older than current subscription revision)
    """
    sub_id = int(job["subscription_id"])
    server_name = str(job["server_name"])
    client_email = str(job["client_email"])
    desired_rev = int(job.get("desired_revision") or 0)
    op = str(job.get("op") or "ensure_client")

    sub = await get_subscription_by_id_only(sub_id)
    if not sub:
        return True, None, False
    current_rev = int(sub.get("sync_revision") or 0)
    if desired_rev < current_rev:
        return True, None, True

    if op == "delete_client":
        found = subscription_manager.server_manager.find_server_by_name(server_name)
        if found is None or found[0] is None:
            return False, f"server {server_name} not available", False
        xui, _ = found
        deleted = await xui.deleteClient(client_email)
        if not deleted:
            # Idempotent: if already absent we treat as success.
            return True, None, False
        return True, None, False

    user_id = await get_user_id_from_subscription_id(sub_id)
    if not user_id:
        return False, "user_id not found for subscription", False
    ok, _created = await subscription_manager.ensure_client_on_server(
        subscription_id=sub_id,
        server_name=server_name,
        client_email=client_email,
        user_id=user_id,
        expires_at=int(sub["expires_at"]),
        token=str(sub["subscription_token"]),
        device_limit=int(sub.get("device_limit") or 1),
        panel_entry=None,
    )
    if not ok:
        return False, "ensure_client returned client_exists=False", False
    return True, None, False


async def process_outbox_once(*, subscription_manager, batch_size: int | None = None, max_attempts: int | None = None) -> dict:
    bs = batch_size if batch_size is not None else _int_env("DARALLA_SYNC_OUTBOX_BATCH_SIZE", 40, 1, 500)
    max_tries = max_attempts if max_attempts is not None else _int_env("DARALLA_SYNC_OUTBOX_MAX_ATTEMPTS", 8, 1, 50)
    jobs = await claim_due_jobs(limit=bs)
    if not jobs:
        return {"claimed": 0, "done": 0, "retried": 0, "dead": 0, "stale": 0}
    done = retried = dead = stale = 0
    for job in jobs:
        job_id = int(job["id"])
        attempts = int(job.get("attempts") or 1)
        try:
            ok, err, is_stale = await _apply_outbox_job(job, subscription_manager=subscription_manager)
            if ok:
                await mark_job_done(job_id)
                done += 1
                if is_stale:
                    stale += 1
                continue
            if attempts >= max_tries:
                await mark_job_dead(job_id, error_text=err or "max attempts reached")
                dead += 1
            else:
                await mark_job_retry(job_id, error_text=err or "apply failed", delay_sec=_backoff_delay_sec(attempts))
                retried += 1
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if attempts >= max_tries:
                await mark_job_dead(job_id, error_text=f"{type(exc).__name__}: {exc}")
                dead += 1
            else:
                await mark_job_retry(
                    job_id,
                    error_text=f"{type(exc).__name__}: {exc}",
                    delay_sec=_backoff_delay_sec(attempts),
                )
                retried += 1
    return {"claimed": len(jobs), "done": done, "retried": retried, "dead": dead, "stale": stale}


async def get_outbox_admin_payload(*, limit: int = 100) -> dict[str, Any]:
    stats = await get_sync_outbox_stats()
    recent_dead = await list_sync_outbox_jobs(status="dead", limit=limit)
    recent_retry = await list_sync_outbox_jobs(status="retry", limit=min(100, limit))
    return {
        "success": True,
        "stats": stats,
        "recent_dead": recent_dead,
        "recent_retry": recent_retry,
    }


async def retry_outbox_dead(*, limit: int = 100) -> dict[str, Any]:
    restarted = await retry_dead_jobs(limit=limit)
    stats = await get_sync_outbox_stats()
    return {"success": True, "retried": restarted, "stats": stats}
