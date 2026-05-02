"""Traffic bucket accounting and enforcement planning."""

from __future__ import annotations

import datetime
import logging
import os
import time

from daralla_backend.db import (
    add_bucket_usage_delta,
    ensure_default_unlimited_bucket,
    get_bucket_used_bytes_for_window,
    get_buckets_for_subscription_servers,
    get_subscription_bucket_states,
    get_subscription_by_id_only,
    get_subscription_servers,
    get_subscription_traffic_snapshot,
    get_subscriptions_to_sync,
    set_subscription_server_bucket,
    upsert_bucket_enforcement_state,
    upsert_subscription_traffic_snapshot,
)
from daralla_backend.services.sync_outbox_service import enqueue_bucket_enforcement_jobs

logger = logging.getLogger(__name__)


def traffic_buckets_enabled() -> bool:
    raw = (os.getenv("DARALLA_TRAFFIC_BUCKETS_ENABLED") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _int_env(name: str, default: int, min_value: int = 1, max_value: int = 1440) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        val = int(raw)
    except ValueError:
        return default
    return max(min_value, min(max_value, val))


def _fmt_compact(bytes_value: int) -> str:
    if bytes_value <= 0:
        return "0B"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(bytes_value)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)}{unit}"
            return f"{value:.1f}{unit}"
        value /= 1024.0
    return f"{int(bytes_value)}B"


class TrafficBucketService:
    """Business logic for bucket usage and per-node policies."""

    async def ensure_default_mapping(self, subscription_id: int) -> None:
        default_bucket_id = await ensure_default_unlimited_bucket(subscription_id)
        servers = await get_subscription_servers(subscription_id)
        server_map = await get_buckets_for_subscription_servers(subscription_id)
        for row in servers:
            server_name = str(row["server_name"])
            if server_name not in server_map:
                await set_subscription_server_bucket(subscription_id, server_name, default_bucket_id)

    async def compute_bucket_states(self, subscription_id: int) -> dict[int, dict]:
        states = await get_subscription_bucket_states(subscription_id)
        result: dict[int, dict] = {}
        for bucket in states:
            bucket_id = int(bucket["id"])
            window_days = int(bucket.get("window_days") or 30)
            used = await get_bucket_used_bytes_for_window(bucket_id, window_days=window_days)
            limit = int(bucket.get("limit_bytes") or 0)
            unlimited = bool(bucket.get("is_unlimited"))
            exhausted = False if unlimited else (limit > 0 and used >= limit)
            await upsert_bucket_enforcement_state(bucket_id, exhausted)
            result[bucket_id] = {
                "bucket": bucket,
                "used_bytes": used,
                "limit_bytes": limit,
                "is_unlimited": unlimited,
                "is_exhausted": exhausted,
                "remaining_bytes": (0 if unlimited else max(0, limit - used)),
            }
        return result

    async def get_subscription_delivery_policy(self, subscription_id: int) -> dict:
        if not traffic_buckets_enabled():
            return {"enabled": False, "allowed_servers": None, "name_suffix_by_server": {}}
        sub = await get_subscription_by_id_only(subscription_id)
        if not sub:
            return {"enabled": False, "allowed_servers": None, "name_suffix_by_server": {}}

        await self.ensure_default_mapping(subscription_id)
        mapping = await get_buckets_for_subscription_servers(subscription_id)
        bucket_states = await self.compute_bucket_states(subscription_id)
        allowed_servers: set[str] = set()
        suffixes: dict[str, str] = {}

        for server_name, bucket in mapping.items():
            bucket_id = int(bucket["id"])
            st = bucket_states.get(bucket_id)
            if not st:
                allowed_servers.add(server_name)
                continue
            # Всегда включаем ноду в подписку: при исчерпании клиент снимается на панели (outbox),
            # но ссылка остаётся в списке с понятной подписью used/limit — пользователь видит «полный» счётчик.
            allowed_servers.add(server_name)
            if st["is_unlimited"]:
                suffixes[server_name] = "[Unlimited]"
            else:
                used_b = int(st.get("used_bytes") or 0)
                lim_b = int(st.get("limit_bytes") or 0)
                ratio = f"[{_fmt_compact(used_b)}/{_fmt_compact(lim_b)}]"
                if st["is_exhausted"]:
                    ratio += " [лимит]"
                suffixes[server_name] = ratio

        return {
            "enabled": True,
            "allowed_servers": allowed_servers,
            "name_suffix_by_server": suffixes,
            "bucket_states": bucket_states,
        }

    async def get_servers_with_exhausted_bucket(self, subscription_id: int) -> set[str]:
        """Имена серверов подписки, у которых лимит bucket исчерпан (жёсткое отключение на панели)."""
        if not traffic_buckets_enabled():
            return set()
        await self.ensure_default_mapping(subscription_id)
        mapping = await get_buckets_for_subscription_servers(subscription_id)
        if not mapping:
            return set()
        states = await self.compute_bucket_states(subscription_id)
        out: set[str] = set()
        for server_name, bucket in mapping.items():
            st = states.get(int(bucket["id"]))
            if not st:
                continue
            if st["is_unlimited"]:
                continue
            if st["is_exhausted"]:
                out.add(str(server_name))
        return out

    async def sync_usage_for_subscription(self, subscription_id: int, *, server_manager) -> dict:
        if not traffic_buckets_enabled():
            return {"enabled": False, "updated_servers": 0, "delta_bytes": 0, "enforcement_jobs": 0}
        if not server_manager:
            return {"enabled": True, "updated_servers": 0, "delta_bytes": 0, "enforcement_jobs": 0}

        await self.ensure_default_mapping(subscription_id)
        servers = await get_subscription_servers(subscription_id)
        mapping = await get_buckets_for_subscription_servers(subscription_id)
        if not servers:
            return {"enabled": True, "updated_servers": 0, "delta_bytes": 0, "enforcement_jobs": 0}

        total_delta = 0
        touched = 0
        for row in servers:
            server_name = str(row["server_name"])
            client_email = str(row["client_email"])
            bucket = mapping.get(server_name)
            if not bucket:
                continue
            found = server_manager.find_server_by_name(server_name)
            if found is None:
                continue
            xui, _ = found
            if not xui:
                continue
            stats = await xui.get_client_traffic(client_email)
            if not stats:
                continue
            cur_up = max(0, int(stats.get("upload", 0)))
            cur_down = max(0, int(stats.get("download", 0)))
            snap = await get_subscription_traffic_snapshot(subscription_id, server_name, client_email)
            prev_up = int((snap or {}).get("last_up", 0))
            prev_down = int((snap or {}).get("last_down", 0))
            delta = (cur_up - prev_up) + (cur_down - prev_down)
            if delta < 0:
                # Панель могла сбросить счетчики после рестарта/reinstall.
                delta = 0
            if delta > 0:
                await add_bucket_usage_delta(int(bucket["id"]), delta)
                total_delta += delta
            await upsert_subscription_traffic_snapshot(
                subscription_id,
                server_name,
                client_email,
                up=cur_up,
                down=cur_down,
            )
            touched += 1

        enforcement_jobs = await self.enqueue_enforcement_if_needed(subscription_id)
        return {
            "enabled": True,
            "updated_servers": touched,
            "delta_bytes": total_delta,
            "enforcement_jobs": enforcement_jobs,
        }

    async def enqueue_enforcement_if_needed(self, subscription_id: int) -> int:
        if not traffic_buckets_enabled():
            return 0
        await self.ensure_default_mapping(subscription_id)
        mapping = await get_buckets_for_subscription_servers(subscription_id)
        if not mapping:
            return 0
        states = await self.compute_bucket_states(subscription_id)
        servers_by_bucket: dict[int, list[str]] = {}
        for server_name, bucket in mapping.items():
            servers_by_bucket.setdefault(int(bucket["id"]), []).append(server_name)

        enqueued = 0
        for bucket_id, server_names in servers_by_bucket.items():
            state = states.get(bucket_id)
            if not state:
                continue
            exhausted = bool(state["is_exhausted"])
            enqueued += await enqueue_bucket_enforcement_jobs(
                subscription_id=subscription_id,
                bucket_id=bucket_id,
                is_exhausted=exhausted,
                server_names=server_names,
                reason="bucket_usage_check",
            )
        return enqueued

    async def sync_usage_for_all_subscriptions(self, *, server_manager) -> dict:
        if not traffic_buckets_enabled():
            return {"enabled": False, "subscriptions": 0, "servers": 0, "delta_bytes": 0, "jobs": 0}
        rows = await get_subscriptions_to_sync()
        subscriptions = 0
        total_servers = 0
        total_delta = 0
        total_jobs = 0
        for sub in rows:
            subscriptions += 1
            try:
                summary = await self.sync_usage_for_subscription(int(sub["id"]), server_manager=server_manager)
                total_servers += int(summary.get("updated_servers", 0))
                total_delta += int(summary.get("delta_bytes", 0))
                total_jobs += int(summary.get("enforcement_jobs", 0))
            except Exception as exc:
                logger.warning("Traffic bucket sync failed for sub=%s: %s", sub.get("id"), exc)
        return {
            "enabled": True,
            "subscriptions": subscriptions,
            "servers": total_servers,
            "delta_bytes": total_delta,
            "jobs": total_jobs,
            "checked_at": int(time.time()),
            "day_utc": datetime.datetime.utcnow().strftime("%Y-%m-%d"),
        }


_SERVICE: TrafficBucketService | None = None


def get_traffic_bucket_service() -> TrafficBucketService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = TrafficBucketService()
    return _SERVICE


def traffic_bucket_sync_interval_seconds() -> int:
    return _int_env("DARALLA_TRAFFIC_BUCKETS_SYNC_INTERVAL_SECONDS", 300, min_value=30, max_value=3600)
