"""Business flow service for admin subscriptions routes."""

from __future__ import annotations

import asyncio
import datetime
import logging
import os

from daralla_backend.db.notifications_db import clear_subscription_notifications
from daralla_backend.db.subscriptions_db import (
    add_subscription_purchased_traffic_bytes,
    adjust_subscription_traffic_quota_for_bucket_usage,
    apply_bucket_usage_adjustment,
    create_subscription_traffic_bucket,
    delete_all_subscription_traffic_data,
    delete_bucket_server_assignments,
    delete_subscription_traffic_bucket,
    ensure_default_unlimited_bucket,
    get_bucket_usage_map_for_subscription,
    get_subscription_by_id_only,
    get_subscription_bucket_states,
    get_subscription_server_bucket_map,
    get_subscription_servers,
    get_subscription_traffic_bucket,
    get_subscription_traffic_quota,
    get_subscriptions_page,
    remove_subscription_server,
    set_subscription_servers_bucket,
    update_subscription_traffic_bucket,
    update_subscription_device_limit,
    update_subscription_expiry,
    update_subscription_name,
    update_subscription_status,
)
from daralla_backend.handlers.api_support.payment_processors import get_globals
from daralla_backend.services.admin_subscriptions_service import (
    delete_subscription_record,
    get_user_id_from_subscriber_id,
    get_user_id_from_subscription_id,
)
from daralla_backend.services.sync_outbox_service import enqueue_subscription_sync_jobs, outbox_write_enabled
from daralla_backend.services.traffic_bucket_service import get_traffic_bucket_service


def serialize_subscription(sub: dict) -> dict:
    return {
        "id": sub["id"],
        "name": (sub.get("name") or "").strip() or f"Подписка {sub['id']}",
        "status": sub["status"],
        "period": sub["period"],
        "device_limit": sub["device_limit"],
        "created_at": sub["created_at"],
        "created_at_formatted": datetime.datetime.fromtimestamp(sub["created_at"]).strftime("%d.%m.%Y %H:%M"),
        "expires_at": sub["expires_at"],
        "expires_at_formatted": datetime.datetime.fromtimestamp(sub["expires_at"]).strftime("%d.%m.%Y %H:%M"),
        "price": sub["price"],
        "token": sub["subscription_token"],
    }


async def list_subscriptions_payload(page: int, limit: int, status: str | None, owner_query: str | None, long_only: bool):
    result = await get_subscriptions_page(
        page=page,
        limit=limit,
        status=status,
        owner_query=owner_query,
        long_only=long_only,
    )
    total = result.get("total", 0)
    items = result.get("items") or []
    subscriptions = []
    for sub in items:
        created_at = sub.get("created_at") or 0
        expires_at = sub.get("expires_at") or 0
        created_at_formatted = datetime.datetime.fromtimestamp(created_at).strftime("%d.%m.%Y %H:%M") if created_at else ""
        expires_at_formatted = datetime.datetime.fromtimestamp(expires_at).strftime("%d.%m.%Y %H:%M") if expires_at else ""
        name = (sub.get("name") or "").strip() or f"Подписка {sub.get('id')}"
        subscriptions.append(
            {
                "id": sub.get("id"),
                "name": name,
                "status": sub.get("status"),
                "period": sub.get("period"),
                "device_limit": sub.get("device_limit"),
                "created_at": created_at,
                "created_at_formatted": created_at_formatted,
                "expires_at": expires_at,
                "expires_at_formatted": expires_at_formatted,
                "price": sub.get("price"),
                "token": sub.get("subscription_token"),
                "user_id": sub.get("user_id"),
                "username": sub.get("username"),
            }
        )
    pages = (total + limit - 1) // limit if limit > 0 else 0
    return {
        "success": True,
        "subscriptions": subscriptions,
        "total": total,
        "page": result.get("page", page),
        "limit": result.get("limit", limit),
        "pages": pages,
        "filters": {
            "status": status,
            "owner_query": owner_query,
            "long_only": long_only,
        },
    }


async def subscription_info_payload(sub_id: int):
    sub = await get_subscription_by_id_only(sub_id)
    if not sub:
        return None
    servers = await get_subscription_servers(sub_id)
    return {
        "success": True,
        "subscription": serialize_subscription(sub),
        "servers": servers,
    }


async def _traffic_bucket_snapshot(sub_id: int) -> dict:
    await ensure_default_unlimited_bucket(sub_id)
    buckets = await get_subscription_bucket_states(sub_id)
    usage_map = await get_bucket_usage_map_for_subscription(sub_id)
    mapping = await get_subscription_server_bucket_map(sub_id)
    for bucket in buckets:
        bucket_id = int(bucket["id"])
        bucket["used_bytes_window"] = int(usage_map.get(bucket_id, 0))
    qrow = await get_subscription_traffic_quota(sub_id)
    traffic_quota = dict(qrow) if qrow else None

    service = get_traffic_bucket_service()
    states = await service.compute_bucket_states(sub_id)
    for bucket in buckets:
        bid = int(bucket["id"])
        st = states.get(bid)
        if not st:
            continue
        bucket["display_used_bytes"] = int(st.get("used_bytes") or 0)
        bucket["display_limit_bytes"] = int(st.get("limit_bytes") or 0)
        bucket["display_remaining_bytes"] = int(st.get("remaining_bytes") or 0)
        bucket["display_exhausted"] = bool(st.get("is_exhausted"))
        bucket["uses_period_quota"] = st.get("traffic_quota") is not None

    return {
        "buckets": buckets,
        "server_bucket_map": mapping,
        "traffic_quota": traffic_quota,
    }


async def subscription_traffic_buckets_payload(sub_id: int):
    sub = await get_subscription_by_id_only(sub_id)
    if not sub:
        return None, {"error": "Subscription not found"}, 404
    snap = await _traffic_bucket_snapshot(sub_id)
    return {"success": True, **snap}, None, None


_BUCKET_WINDOW_DAYS_FIXED = 30
_BUCKET_CREDIT_PERIODS_FIXED = 1


def _with_fixed_bucket_technical_fields(updates: dict) -> dict:
    """Окно/кредит — служебные поля схемы; лимит по подписке задаётся квотой. Фиксируем и игнорируем ввод из API."""
    out = dict(updates or {})
    for k in ("window_days", "credit_periods_total", "credit_periods_remaining"):
        out.pop(k, None)
    out["window_days"] = _BUCKET_WINDOW_DAYS_FIXED
    out["credit_periods_total"] = _BUCKET_CREDIT_PERIODS_FIXED
    out["credit_periods_remaining"] = _BUCKET_CREDIT_PERIODS_FIXED
    return out


async def create_subscription_traffic_bucket_payload(sub_id: int, data: dict):
    sub = await get_subscription_by_id_only(sub_id)
    if not sub:
        return None, {"error": "Subscription not found"}, 404
    name = str((data or {}).get("name") or "").strip()
    if not name:
        return None, {"error": "Bucket name is required"}, 400
    limit_bytes = int((data or {}).get("limit_bytes") or 0)
    is_unlimited = bool((data or {}).get("is_unlimited", False))
    if not is_unlimited and limit_bytes <= 0:
        return None, {"error": "limit_bytes must be > 0 for limited bucket"}, 400
    bucket_id = await create_subscription_traffic_bucket(
        sub_id,
        name=name,
        limit_bytes=limit_bytes,
        is_unlimited=is_unlimited,
        window_days=_BUCKET_WINDOW_DAYS_FIXED,
        credit_periods_total=_BUCKET_CREDIT_PERIODS_FIXED,
    )
    snap = await _traffic_bucket_snapshot(sub_id)
    return {"success": True, "bucket_id": bucket_id, **snap}, None, None


def _validate_traffic_bucket_update_patch(bucket: dict, updates: dict) -> str | None:
    """Возвращает текст ошибки на русском или None (название, лимит, безлимит, вкл/выкл учёта)."""
    eff_limit = int(bucket.get("limit_bytes") or 0)
    eff_unl = bool(int(bucket.get("is_unlimited") or 0))

    if "name" in updates:
        eff_name = str(updates.get("name") or "").strip()
        if not eff_name:
            return "Укажите название пакета"
    if "limit_bytes" in updates:
        eff_limit = max(0, int(updates.get("limit_bytes") or 0))
    if "is_unlimited" in updates:
        eff_unl = bool(updates.get("is_unlimited"))

    if not eff_unl and eff_limit <= 0:
        return "Для лимитированного пакета укажите положительный лимит трафика (байты)"
    return None


async def update_subscription_traffic_bucket_payload(sub_id: int, bucket_id: int, data: dict):
    sub = await get_subscription_by_id_only(sub_id)
    if not sub:
        return None, {"error": "Subscription not found"}, 404
    bucket = await get_subscription_traffic_bucket(bucket_id)
    if not bucket or int(bucket.get("subscription_id") or 0) != int(sub_id):
        return None, {"error": "Bucket not found"}, 404
    updates = _with_fixed_bucket_technical_fields(dict(data or {}))
    err = _validate_traffic_bucket_update_patch(bucket, updates)
    if err:
        return None, {"error": err}, 400
    ok = await update_subscription_traffic_bucket(bucket_id, updates)
    if not ok:
        return None, {"error": "Нет допустимых полей для обновления"}, 400
    service = get_traffic_bucket_service()
    await service.enqueue_enforcement_if_needed(sub_id)
    snap = await _traffic_bucket_snapshot(sub_id)
    return {"success": True, "bucket_id": bucket_id, **snap}, None, None


async def assign_subscription_servers_bucket_payload(sub_id: int, bucket_id: int, server_names: list[str]):
    sub = await get_subscription_by_id_only(sub_id)
    if not sub:
        return None, {"error": "Subscription not found"}, 404
    bucket = await get_subscription_traffic_bucket(bucket_id)
    if not bucket or int(bucket.get("subscription_id") or 0) != int(sub_id):
        return None, {"error": "Bucket not found"}, 404
    cleaned = [str(s).strip() for s in (server_names or []) if str(s).strip()]
    sub_servers = await get_subscription_servers(sub_id)
    allowed = {str(row["server_name"]).strip() for row in sub_servers if str(row.get("server_name") or "").strip()}
    for name in cleaned:
        if name not in allowed:
            return None, {"error": f"Нода «{name}» не привязана к этой подписке"}, 400
    await set_subscription_servers_bucket(sub_id, cleaned, bucket_id)
    service = get_traffic_bucket_service()
    await service.enqueue_enforcement_if_needed(sub_id)
    snap = await _traffic_bucket_snapshot(sub_id)
    return {"success": True, "assigned": len(cleaned), **snap}, None, None


async def clear_subscription_bucket_servers_payload(sub_id: int, bucket_id: int):
    sub = await get_subscription_by_id_only(sub_id)
    if not sub:
        return None, {"error": "Subscription not found"}, 404
    bucket = await get_subscription_traffic_bucket(bucket_id)
    if not bucket or int(bucket.get("subscription_id") or 0) != int(sub_id):
        return None, {"error": "Bucket not found"}, 404
    deleted = await delete_bucket_server_assignments(sub_id, bucket_id)
    default_id = await ensure_default_unlimited_bucket(sub_id)
    servers = await get_subscription_servers(sub_id)
    mapping = await get_subscription_server_bucket_map(sub_id)
    for server in servers:
        server_name = str(server["server_name"])
        if server_name not in mapping:
            await set_subscription_servers_bucket(sub_id, [server_name], default_id)
    service = get_traffic_bucket_service()
    await service.enqueue_enforcement_if_needed(sub_id)
    snap = await _traffic_bucket_snapshot(sub_id)
    return {"success": True, "unassigned": deleted, **snap}, None, None


async def adjust_subscription_bucket_usage_payload(sub_id: int, bucket_id: int, bytes_delta: int, reason: str = ""):
    sub = await get_subscription_by_id_only(sub_id)
    if not sub:
        return None, {"error": "Subscription not found"}, 404
    bucket = await get_subscription_traffic_bucket(bucket_id)
    if not bucket or int(bucket.get("subscription_id") or 0) != int(sub_id):
        return None, {"error": "Bucket not found"}, 404
    await apply_bucket_usage_adjustment(bucket_id, int(bytes_delta), reason=reason or "admin_adjust")
    await adjust_subscription_traffic_quota_for_bucket_usage(sub_id, int(bucket_id), int(bytes_delta))
    service = get_traffic_bucket_service()
    await service.enqueue_enforcement_if_needed(sub_id)
    snap = await _traffic_bucket_snapshot(sub_id)
    return {"success": True, "bucket_id": bucket_id, **snap}, None, None


async def add_subscription_purchased_traffic_payload(sub_id: int, add_bytes: int):
    sub = await get_subscription_by_id_only(sub_id)
    if not sub:
        return None, {"error": "Subscription not found"}, 404
    try:
        ab = int(add_bytes)
    except (TypeError, ValueError):
        ab = 0
    if ab <= 0:
        return None, {"error": "add_bytes must be positive"}, 400
    updated = await add_subscription_purchased_traffic_bytes(sub_id, ab)
    if updated is None:
        return None, {"error": "Нет строки квоты трафика для этой подписки"}, 400
    service = get_traffic_bucket_service()
    await service.enqueue_enforcement_if_needed(sub_id)
    snap = await _traffic_bucket_snapshot(sub_id)
    return {"success": True, **snap}, None, None


async def delete_subscription_traffic_bucket_payload(sub_id: int, bucket_id: int):
    sub = await get_subscription_by_id_only(sub_id)
    if not sub:
        return None, {"error": "Subscription not found"}, 404
    ok, err = await delete_subscription_traffic_bucket(sub_id, bucket_id)
    if not ok:
        if err == "not_found":
            return None, {"error": "Bucket not found"}, 404
        if err == "protected_unlimited":
            return None, {"error": "Нельзя удалить пакет без лимита трафика"}, 400
        if err == "last_bucket":
            return None, {"error": "Нельзя удалить последний пакет трафика"}, 400
        return None, {"error": "Не удалось удалить пакет"}, 400
    service = get_traffic_bucket_service()
    await service.enqueue_enforcement_if_needed(sub_id)
    snap = await _traffic_bucket_snapshot(sub_id)
    return {"success": True, **snap}, None, None


def _validate_status_transition(old_status: str, new_status: str):
    if old_status in ("active", "expired") and new_status in ("active", "expired") and old_status != new_status:
        return (
            "Нельзя вручную менять статус между \"active\" и \"expired\". "
            "Статус обновляется автоматически при изменении даты истечения (expires_at)."
        )
    if new_status != "deleted" and old_status == "deleted":
        return f"Нельзя изменить статус \"{old_status}\" на \"{new_status}\". Статус \"deleted\" является финальным."
    return None


async def _sync_after_update(
    sub_id: int,
    updated_sub: dict,
    old_status: str,
    old_expires_at: int,
    old_device_limit: int,
    updates: dict,
    logger: logging.Logger,
) -> None:
    managers = get_globals()
    server_manager = managers.get("server_manager")
    subscription_manager = managers.get("subscription_manager")

    if not server_manager or not subscription_manager:
        logger.warning("server_manager или subscription_manager не доступны для синхронизации")
        return

    servers = await get_subscription_servers(sub_id)
    if not servers:
        logger.info("Подписка %s не имеет привязанных серверов, синхронизация не требуется", sub_id)
        return

    subscriber_id = updated_sub.get("subscriber_id")
    if not subscriber_id:
        logger.warning("Подписка %s не имеет subscriber_id, синхронизация невозможна", sub_id)
        return

    user_id = await get_user_id_from_subscriber_id(subscriber_id)
    if not user_id:
        logger.warning("Не найден user_id для subscriber_id=%s", subscriber_id)
        return

    new_status = updated_sub["status"]
    new_expires_at = updated_sub["expires_at"]
    new_device_limit = updated_sub["device_limit"]
    token = updated_sub["subscription_token"]

    if new_status in ["expired", "deleted"] and old_status != new_status:
        logger.info("Статус подписки %s изменился на %s, удаляем клиентов с серверов", sub_id, new_status)

        async def delete_clients_with_timeout():
            deleted_count = 0
            failed_count = 0
            for server_info in servers:
                server_name = server_info["server_name"]
                client_email = server_info["client_email"]
                try:
                    xui, _ = server_manager.get_server_by_name(server_name)
                    if xui:
                        try:
                            await asyncio.wait_for(xui.deleteClient(client_email, 5), timeout=8.0)
                            deleted_count += 1
                        except asyncio.TimeoutError:
                            failed_count += 1
                        except Exception:
                            failed_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    logger.error("Ошибка при удалении клиента %s с сервера %s: %s", client_email, server_name, e)
                    failed_count += 1
            return deleted_count, failed_count

        try:
            deleted_count, failed_count = await asyncio.wait_for(delete_clients_with_timeout(), timeout=30.0)
        except asyncio.TimeoutError:
            logger.error("Таймаут при удалении клиентов для подписки %s", sub_id)
            deleted_count = 0
            failed_count = len(servers)
        except Exception as e:
            logger.error("Ошибка при удалении клиентов для подписки %s: %s", sub_id, e)
            deleted_count = 0
            failed_count = len(servers)

        # Для expired удаляем клиентов с панелей, но сохраняем связи subscription_servers,
        # чтобы при продлении можно было автоматически восстановить клиентов.
        # Связи удаляем только для deleted.
        if new_status == "deleted" and (deleted_count > 0 or failed_count < len(servers)):
            for server_info in servers:
                server_name = server_info["server_name"]
                try:
                    await remove_subscription_server(sub_id, server_name)
                except Exception as e:
                    logger.error("Ошибка удаления связи подписки %s с сервером %s: %s", sub_id, server_name, e)

    elif new_status == "active" and old_status != "active" and old_status != "deleted":
        logger.info("Статус подписки %s изменился на active, создаем/восстанавливаем клиентов", sub_id)
        for server_info in servers:
            server_name = server_info["server_name"]
            client_email = server_info["client_email"]
            try:
                await subscription_manager.ensure_client_on_server(
                    subscription_id=sub_id,
                    server_name=server_name,
                    client_email=client_email,
                    user_id=user_id,
                    expires_at=new_expires_at,
                    token=token,
                    device_limit=new_device_limit,
                )
            except Exception as e:
                logger.error("Ошибка создания/обновления клиента %s на сервере %s: %s", client_email, server_name, e)

    if ("expires_at" in updates or "device_limit" in updates) and new_status == "active":
        if old_status == "active" or (old_status == "expired" and "expires_at" in updates):
            for server_info in servers:
                server_name = server_info["server_name"]
                client_email = server_info["client_email"]
                try:
                    await subscription_manager.ensure_client_on_server(
                        subscription_id=sub_id,
                        server_name=server_name,
                        client_email=client_email,
                        user_id=user_id,
                        expires_at=new_expires_at,
                        token=token,
                        device_limit=new_device_limit,
                    )
                except Exception as e:
                    logger.error("Ошибка синхронизации клиента %s на сервере %s: %s", client_email, server_name, e)


async def update_subscription_payload(sub_id: int, updates: dict, logger: logging.Logger):
    if not updates:
        return None, {"error": "No fields to update"}, 400

    sub = await get_subscription_by_id_only(sub_id)
    if not sub:
        return None, {"error": "Subscription not found"}, 404

    old_status = sub["status"]
    old_expires_at = sub["expires_at"]
    old_device_limit = sub["device_limit"]

    if "status" in updates:
        err = _validate_status_transition(old_status, updates["status"])
        if err:
            return None, {"error": err}, 400

    if "name" in updates:
        await update_subscription_name(sub_id, updates["name"])
    if "expires_at" in updates:
        await update_subscription_expiry(sub_id, updates["expires_at"])
    if "device_limit" in updates:
        await update_subscription_device_limit(sub_id, updates["device_limit"])
    if "status" in updates and updates["status"] == "deleted":
        await update_subscription_status(sub_id, updates["status"])
        await clear_subscription_notifications(sub_id)

    updated_sub = await get_subscription_by_id_only(sub_id)
    outbox_enqueued = 0
    if outbox_write_enabled():
        try:
            outbox_enqueued = await enqueue_subscription_sync_jobs(
                int(sub_id),
                reason="admin_subscription_update",
            )
        except Exception as outbox_e:
            logger.warning("Не удалось поставить outbox jobs для sub=%s: %s", sub_id, outbox_e)

    # Не блокируем HTTP-ответ синхронизацией: в мобильном WebView долгий запрос часто
    # обрывается как "Load failed", хотя данные уже сохранены в БД.
    async def _sync_in_background():
        try:
            await asyncio.wait_for(
                _sync_after_update(sub_id, updated_sub, old_status, old_expires_at, old_device_limit, updates, logger),
                timeout=60.0,
            )
        except asyncio.TimeoutError:
            logger.error("Таймаут при фоновой синхронизации подписки %s", sub_id)
        except Exception as sync_e:
            logger.error("Ошибка при фоновой синхронизации подписки %s: %s", sub_id, sync_e, exc_info=True)

    fallback_enabled = (os.getenv("DARALLA_SYNC_OUTBOX_USE_LEGACY_SYNC_FALLBACK", "1").strip() != "0")
    if fallback_enabled:
        asyncio.create_task(_sync_in_background())

    return {
        "success": True,
        "subscription": serialize_subscription(updated_sub),
        "sync_outbox_enqueued": outbox_enqueued,
        "legacy_sync_fallback": fallback_enabled,
    }, None, None


async def manual_sync_payload(sub_id: int, logger: logging.Logger):
    sub = await get_subscription_by_id_only(sub_id)
    if not sub:
        return None, {"error": "Subscription not found"}, 404
    servers = await get_subscription_servers(sub_id)
    from daralla_backend.app_context import get_ctx

    subscription_manager = get_ctx().subscription_manager
    if not subscription_manager:
        return None, {"error": "Subscription manager not available"}, 503

    user_id = await get_user_id_from_subscription_id(sub_id)
    sync_results = []
    for server_info in servers:
        server_name = server_info["server_name"]
        client_email = server_info["client_email"]
        try:
            await subscription_manager.ensure_client_on_server(
                subscription_id=sub_id,
                server_name=server_name,
                client_email=client_email,
                user_id=user_id,
                expires_at=sub["expires_at"],
                token=sub["subscription_token"],
                device_limit=sub["device_limit"],
            )
            subscription_name = (sub.get("name") or "").strip() or sub["subscription_token"]
            xui, _ = subscription_manager.server_manager.get_server_by_name(server_name)
            if xui:
                try:
                    client_info = await xui.get_client_info(client_email)
                    if client_info:
                        current_sub_id = client_info["client"].get("subId", "")
                        if current_sub_id != subscription_name:
                            await xui.updateClientName(client_email, subscription_name)
                except Exception as name_sync_e:
                    logger.warning("Ошибка синхронизации имени подписки на сервере %s: %s", server_name, name_sync_e)
            sync_results.append({"server": server_name, "status": "success"})
        except Exception as e:
            logger.error("Ошибка синхронизации с сервером %s: %s", server_name, e)
            sync_results.append({"server": server_name, "status": "error", "error": str(e)})
    return {"success": True, "sync_results": sync_results}, None, None


async def delete_subscription_payload(sub_id: int):
    sub = await get_subscription_by_id_only(sub_id)
    if not sub:
        return None, {"error": "Subscription not found"}, 404
    servers = await get_subscription_servers(sub_id)
    from daralla_backend.app_context import get_ctx

    server_manager = get_ctx().server_manager

    deleted = []
    failed = []
    if server_manager and servers:
        for server_info in servers:
            server_name = server_info["server_name"]
            client_email = server_info["client_email"]
            try:
                xui, _ = server_manager.get_server_by_name(server_name)
                if xui:
                    deleted_ok = await xui.deleteClient(client_email, timeout=30)
                    if deleted_ok:
                        deleted.append(server_name)
                    else:
                        failed.append(server_name)
                else:
                    failed.append(server_name)
            except Exception:
                failed.append(server_name)

    for server_info in servers:
        try:
            await remove_subscription_server(sub_id, server_info["server_name"])
        except Exception:
            pass

    await delete_all_subscription_traffic_data(sub_id)
    await delete_subscription_record(sub_id)
    return {
        "success": True,
        "message": "Подписка удалена",
        "deleted_servers": deleted,
        "failed_servers": failed,
    }, None, None
