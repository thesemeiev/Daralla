"""Service layer for admin server/group management routes."""

from __future__ import annotations

import asyncio
import logging
import sqlite3

from daralla_backend.app_context import get_ctx
from daralla_backend.client_flow import normalize_client_flow_for_storage
from daralla_backend.db.servers_db import (
    add_server_config,
    add_server_group,
    delete_server_config,
    get_group_load_statistics,
    get_server_by_id,
    get_server_group_traffic_limited_servers,
    get_server_group_traffic_template,
    get_server_groups,
    get_servers_config,
    reorder_servers_in_group,
    replace_server_group_traffic_limited_servers,
    update_server_config,
    update_server_group,
    upsert_server_group_traffic_template,
)
from daralla_backend.db.subscriptions_db import sync_subscription_statuses
from daralla_backend.services.group_traffic_template_service import (
    apply_group_traffic_template_bulk,
)
from daralla_backend.services.server_provider import ServerProvider
from daralla_backend.services.sync_outbox_service import (
    enqueue_group_sync_jobs,
    get_outbox_admin_payload,
    process_outbox_once,
    retry_outbox_dead,
)
from daralla_backend.services.xui_service import X3

logger = logging.getLogger(__name__)
_SERVER_CONFIG_OP_LOCK = asyncio.Lock()


def _json_conflict_from_integrity(exc: sqlite3.IntegrityError) -> tuple[dict, int] | None:
    s = str(exc)
    if "servers_config.name" in s:
        return (
            {
                "success": False,
                "error": "Сервер с таким идентификатором уже есть. Поле «Имя» уникально для всех групп.",
            },
            409,
        )
    if "server_groups.name" in s:
        return ({"success": False, "error": "Группа с таким именем уже существует."}, 409)
    if "UNIQUE constraint failed" in s:
        return (
            {
                "success": False,
                "error": "Такая запись уже есть в базе (ограничение уникальности).",
            },
            409,
        )
    return None


async def _background_sync_client_flow(server_id: int) -> None:
    try:
        server = await get_server_by_id(int(server_id))
        if not server:
            logger.warning("background flow sync: server_id=%s не найден", server_id)
            return
        x3 = X3(
            login=server["login"],
            password=server["password"],
            host=server["host"],
            vpn_host=server.get("vpn_host"),
            subscription_port=server.get("subscription_port", 2096),
            subscription_url=server.get("subscription_url"),
        )
        flow_val = (server.get("client_flow") or "").strip() or ""
        updated, skipped, errs = await x3.sync_flow_for_all_clients(flow_val)
        logger.info(
            "Фоновый sync flow завершён: server_id=%s updated=%s skipped=%s errors=%s",
            server_id,
            updated,
            skipped,
            len(errs),
        )
        if errs:
            logger.warning(
                "Фоновый sync flow server_id=%s примеры ошибок: %s",
                server_id,
                errs[:5],
            )
    except Exception:
        logger.exception("Фоновый sync flow server_id=%s завершился ошибкой", server_id)


def _coerce_server_active(value) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    try:
        return int(value) == 1
    except (TypeError, ValueError):
        return False


async def _reload_server_manager() -> None:
    ctx = get_ctx()
    server_manager = ctx.server_manager
    if not server_manager:
        return
    new_config = await ServerProvider.get_all_servers_by_group()
    server_manager.init_from_config(new_config)


def _was_inactive_and_now_active(old_server: dict | None, update_data: dict) -> bool:
    if not old_server or "is_active" not in update_data:
        return False
    old_on = _coerce_server_active(old_server.get("is_active"))
    new_on = _coerce_server_active(update_data.get("is_active"))
    return (not old_on) and new_on


async def _run_sync_servers_with_config() -> tuple[dict | None, str | None]:
    ctx = get_ctx()
    sync_manager = ctx.sync_manager
    sub = ctx.subscription_manager
    if sync_manager:
        try:
            status_sync = await sync_subscription_statuses()
            await sync_manager.cleanup_expired_subscriptions(days_limit=3)
            stats = await sync_manager.sync_all_subscriptions(auto_fix=True)
            if isinstance(stats, dict):
                stats["status_sync"] = status_sync
            return stats, None
        except Exception as exc:
            logger.exception("Полный sync после изменения сервера завершился ошибкой: %s", exc)
            return None, str(exc)

    if not sub:
        return None, "subscription_manager unavailable"
    try:
        stats = await sub.sync_servers_with_config(auto_create_clients=True)
        return stats, None
    except Exception as exc:
        logger.exception("sync_servers_with_config после изменения сервера: %s", exc)
        return None, str(exc)


async def _reload_and_sync_serialized(need_sync: bool) -> tuple[dict | None, str | None, bool]:
    async with _SERVER_CONFIG_OP_LOCK:
        try:
            await _reload_server_manager()
        except Exception as mgr_e:
            logger.error("Ошибка обновления менеджера серверов: %s", mgr_e)

        if not need_sync:
            return None, None, False

        sync_stats, sync_error = await _run_sync_servers_with_config()
        return sync_stats, sync_error, False


async def handle_server_groups(data: dict):
    action = data.get("action", "list")
    if action == "list":
        groups = await get_server_groups(only_active=False)
        stats = await get_group_load_statistics()
        return {"success": True, "groups": groups, "stats": stats}, 200
    if action == "add":
        name = data.get("name")
        description = data.get("description")
        is_default = data.get("is_default", False)
        if not name:
            return {"error": "Name is required"}, 400
        try:
            group_id = await add_server_group(name, description, is_default)
        except sqlite3.IntegrityError as exc:
            pair = _json_conflict_from_integrity(exc)
            if pair:
                return pair
            raise
        return {"success": True, "group_id": group_id}, 200
    return {"error": "Invalid action"}, 400


async def handle_server_group_update(data: dict):
    group_id = data.get("id")
    if not group_id:
        return {"error": "Group ID is required"}, 400
    try:
        await update_server_group(
            group_id,
            name=data.get("name"),
            description=data.get("description"),
            is_active=data.get("is_active"),
            is_default=data.get("is_default"),
        )
    except sqlite3.IntegrityError as exc:
        pair = _json_conflict_from_integrity(exc)
        if pair:
            return pair
        raise
    try:
        await enqueue_group_sync_jobs(int(group_id), reason="admin_group_update")
    except Exception as e:
        logger.warning("Outbox enqueue group update failed group=%s: %s", group_id, e)
    return {"success": True}, 200


async def handle_servers_config(data: dict):
    action = data.get("action", "list")
    if action == "list":
        group_id = data.get("group_id")
        servers = await get_servers_config(group_id=group_id, only_active=False)
        return {"success": True, "servers": servers}, 200
    if action == "add":
        group_id = data.get("group_id")
        name = data.get("name")
        host = data.get("host")
        login = data.get("login")
        password = data.get("password")
        if not all([group_id, name, host, login, password]):
            return {"error": "All fields are required"}, 400
        cf_norm, cf_err = normalize_client_flow_for_storage(data.get("client_flow"))
        if cf_err:
            return {"error": cf_err}, 400
        raw_active = data.get("is_active")
        insert_active = 1 if (raw_active is None or _coerce_server_active(raw_active)) else 0
        try:
            server_id = await add_server_config(
                group_id,
                name,
                host,
                login,
                password,
                display_name=data.get("display_name"),
                vpn_host=data.get("vpn_host"),
                lat=data.get("lat"),
                lng=data.get("lng"),
                subscription_port=data.get("subscription_port"),
                subscription_url=data.get("subscription_url") or None,
                client_flow=cf_norm,
                map_label=data.get("map_label") or None,
                location=data.get("location") or None,
                max_concurrent_clients=data.get("max_concurrent_clients"),
                is_active=insert_active,
            )
        except sqlite3.IntegrityError as exc:
            pair = _json_conflict_from_integrity(exc)
            if pair:
                return pair
            raise
        sync_stats, sync_error, sync_debounced = await _reload_and_sync_serialized(
            need_sync=(insert_active == 1)
        )
        try:
            await enqueue_group_sync_jobs(int(group_id), reason="admin_server_add")
        except Exception as e:
            logger.warning("Outbox enqueue server add failed group=%s: %s", group_id, e)
        payload = {"success": True, "server_id": server_id}
        if sync_stats is not None:
            payload["sync_stats"] = sync_stats
        if sync_error:
            payload["sync_error"] = sync_error
        if sync_debounced:
            payload["sync_debounced"] = True
        return payload, 200
    if action == "reorder":
        group_id = data.get("group_id")
        server_ids = data.get("server_ids")
        if group_id is None or not isinstance(server_ids, list) or len(server_ids) == 0:
            return {"error": "group_id and server_ids[] required"}, 400
        ok = await reorder_servers_in_group(int(group_id), server_ids)
        if not ok:
            return {"error": "Invalid order or group mismatch"}, 400
        await _reload_and_sync_serialized(need_sync=False)
        return {"success": True}, 200
    return {"error": "Invalid action"}, 400


async def handle_server_config_update(data: dict):
    server_id = data.get("id")
    if not server_id:
        return {"error": "Server ID is required"}, 400

    update_data = {k: v for k, v in data.items() if k not in ("initData", "id")}
    if "client_flow" in update_data:
        cf_norm, cf_err = normalize_client_flow_for_storage(update_data.get("client_flow"))
        if cf_err:
            return {"error": cf_err}, 400
        update_data["client_flow"] = cf_norm
    old_server = await get_server_by_id(int(server_id))

    client_flow_changed = False
    if "client_flow" in update_data and old_server is not None:
        old_cf = ((old_server.get("client_flow") or "").strip() or None)
        new_cf = update_data["client_flow"]
        client_flow_changed = old_cf != new_cf
    try:
        await update_server_config(server_id, **update_data)
    except sqlite3.IntegrityError as exc:
        pair = _json_conflict_from_integrity(exc)
        if pair:
            return pair
        raise
    sync_stats, sync_error, sync_debounced = await _reload_and_sync_serialized(
        need_sync=_was_inactive_and_now_active(old_server, update_data)
    )
    try:
        if old_server and old_server.get("group_id") is not None:
            await enqueue_group_sync_jobs(int(old_server["group_id"]), reason="admin_server_update")
    except Exception as e:
        logger.warning("Outbox enqueue server update failed server=%s: %s", server_id, e)
    payload = {
        "success": True,
        "client_flow_changed": client_flow_changed,
        "server_id": int(server_id),
    }
    if sync_stats is not None:
        payload["sync_stats"] = sync_stats
    if sync_error:
        payload["sync_error"] = sync_error
    if sync_debounced:
        payload["sync_debounced"] = True
    if client_flow_changed:
        asyncio.create_task(_background_sync_client_flow(int(server_id)))
        payload["flow_sync_started"] = True
    return payload, 200


async def handle_server_config_sync_flow(data: dict):
    server_id = data.get("server_id") or data.get("id")
    if not server_id:
        return {"error": "server_id is required"}, 400
    server = await get_server_by_id(int(server_id))
    if not server:
        return {"error": "Server not found"}, 404
    x3 = X3(
        login=server["login"],
        password=server["password"],
        host=server["host"],
        vpn_host=server.get("vpn_host"),
        subscription_port=server.get("subscription_port", 2096),
        subscription_url=server.get("subscription_url"),
    )
    flow_val = (server.get("client_flow") or "").strip() or ""
    updated, skipped, errs = await x3.sync_flow_for_all_clients(flow_val)
    return {
        "success": True,
        "updated": updated,
        "skipped": skipped,
        "errors": errs[:20],
    }, 200


async def handle_server_config_delete(data: dict):
    server_id = data.get("id")
    if not server_id:
        return {"error": "Server ID is required"}, 400
    old_server = await get_server_by_id(int(server_id))
    await delete_server_config(server_id)
    sync_stats, sync_error, sync_debounced = await _reload_and_sync_serialized(need_sync=True)
    try:
        if old_server and old_server.get("group_id") is not None:
            await enqueue_group_sync_jobs(int(old_server["group_id"]), reason="admin_server_delete")
    except Exception as e:
        logger.warning("Outbox enqueue server delete failed server=%s: %s", server_id, e)
    payload = {"success": True}
    if sync_stats is not None:
        payload["sync_stats"] = sync_stats
    if sync_error:
        payload["sync_error"] = sync_error
    if sync_debounced:
        payload["sync_debounced"] = True
    return payload, 200


async def handle_server_group_traffic_template(data: dict):
    """action: get | save | apply — шаблон трафика для группы серверов."""
    data = data or {}
    action = str(data.get("action") or "get").strip().lower()
    group_id = data.get("group_id")
    if group_id is None or group_id == "":
        return {"error": "group_id is required"}, 400
    try:
        gid = int(group_id)
    except (TypeError, ValueError):
        return {"error": "Invalid group_id"}, 400

    if action == "get":
        row = await get_server_group_traffic_template(gid)
        limited = await get_server_group_traffic_limited_servers(gid)
        tpl = dict(row) if row else None
        return {"success": True, "template": tpl, "limited_server_names": limited}, 200

    if action == "save":
        enabled = bool(data.get("enabled"))
        limited_bucket_name = str(data.get("limited_bucket_name") or "Лимитированные ноды").strip()
        limit_bytes = int(data.get("limit_bytes") or 0)
        is_unlimited = bool(data.get("is_unlimited"))
        # Включённый трафик привязан к оплаченному периоду подписки (квота), не к «окну» bucket.
        # Поля window_days / credit в таблице buckets — наследие схемы; для шаблона фиксируем.
        window_days = 30
        credit_periods_total = 1
        raw_names = data.get("limited_server_names")
        if raw_names is None:
            raw_names = []
        if not isinstance(raw_names, list):
            return {"error": "limited_server_names must be a list"}, 400
        cleaned = [str(s).strip() for s in raw_names if str(s).strip()]

        servers = await get_servers_config(group_id=gid, only_active=False)
        valid = {str(s["name"]) for s in (servers or [])}
        for name in cleaned:
            if name not in valid:
                return {"error": f"Сервер не в группе: {name}"}, 400

        if cleaned and not is_unlimited and limit_bytes <= 0:
            return {"error": "Укажите limit_bytes > 0 или включите is_unlimited"}, 400

        await upsert_server_group_traffic_template(
            gid,
            enabled=enabled,
            limited_bucket_name=limited_bucket_name,
            limit_bytes=max(0, limit_bytes),
            is_unlimited=is_unlimited,
            window_days=max(1, window_days),
            credit_periods_total=max(1, credit_periods_total),
        )
        await replace_server_group_traffic_limited_servers(gid, cleaned)
        return {"success": True}, 200

    if action == "apply":
        force = bool(data.get("force"))
        dry_run = bool(data.get("dry_run"))
        raw_subs = data.get("subscription_ids")
        sub_ids = None
        if raw_subs is not None:
            if not isinstance(raw_subs, list):
                return {"error": "subscription_ids must be a list"}, 400
            try:
                sub_ids = [int(x) for x in raw_subs]
            except (TypeError, ValueError):
                return {"error": "Invalid subscription_ids"}, 400
        result = await apply_group_traffic_template_bulk(
            gid,
            subscription_ids=sub_ids,
            force=force,
            dry_run=dry_run,
        )
        return result, 200

    return {"error": "Invalid action"}, 400


async def handle_sync_all():
    sync_manager = get_ctx().sync_manager
    if not sync_manager:
        return {"error": "Sync manager not available"}, 503
    stats = await sync_manager.sync_all_subscriptions(auto_fix=True)
    return {"success": True, "stats": stats}, 200


async def handle_sync_outbox(data: dict):
    action = str((data or {}).get("action") or "stats").strip().lower()
    if action == "stats":
        limit = data.get("limit", 100)
        payload = await get_outbox_admin_payload(limit=int(limit))
        return payload, 200
    if action == "retry_dead":
        limit = data.get("limit", 100)
        payload = await retry_outbox_dead(limit=int(limit))
        return payload, 200
    if action == "process_once":
        ctx = get_ctx()
        sub_mgr = ctx.subscription_manager
        if not sub_mgr:
            return {"success": False, "error": "subscription_manager unavailable"}, 503
        summary = await process_outbox_once(subscription_manager=sub_mgr)
        return {"success": True, "summary": summary}, 200
    return {"success": False, "error": "Invalid action"}, 400
