"""
Quart Blueprint: admin server-groups, server-group/update, servers-config,
server-config/update, server-config/sync-flow, server-config/delete, sync-all.
"""
import asyncio
import logging

from quart import Blueprint, request, jsonify

from bot.web.routes.admin_common import _cors_headers, admin_route
from bot.db.servers_db import (
    get_server_groups,
    add_server_group,
    get_group_load_statistics,
    update_server_group,
    get_servers_config,
    add_server_config,
    get_server_by_id,
    update_server_config,
    delete_server_config,
    reorder_servers_in_group,
)
from bot.db.subscriptions_db import sync_subscription_statuses
from bot.services.server_provider import ServerProvider
from bot.services.xui_service import X3
from bot.app_context import get_ctx
from bot.client_flow import normalize_client_flow_for_storage

logger = logging.getLogger(__name__)
_SERVER_CONFIG_OP_LOCK = asyncio.Lock()


async def _background_sync_client_flow(server_id: int) -> None:
    """Фоновая синхронизация flow по всем клиентам панели после смены client_flow в конфиге."""
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
    """True если сервер считается активным (is_active в БД)."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    try:
        return int(value) == 1
    except (TypeError, ValueError):
        return False


async def _reload_server_manager() -> None:
    """Перечитывает активные серверы из БД в MultiServerManager."""
    ctx = get_ctx()
    sm = ctx.server_manager
    if not sm:
        return
    new_config = await ServerProvider.get_all_servers_by_group()
    sm.init_from_config(new_config)


def _was_inactive_and_now_active(old_server: dict | None, update_data: dict) -> bool:
    """Переход is_active с выключенного на включённый в одном запросе update."""
    if not old_server or "is_active" not in update_data:
        return False
    old_on = _coerce_server_active(old_server.get("is_active"))
    new_on = _coerce_server_active(update_data.get("is_active"))
    return (not old_on) and new_on


async def _run_sync_servers_with_config() -> tuple[dict | None, str | None]:
    """
    Догон подписок по текущему конфигу (новая/включённая нода).
    При наличии sync_manager запускает расширенный цикл:
    1) sync статусов active/expired
    2) cleanup подписок, просроченных > 3 дней
    3) полный sync подписок/клиентов
    Возвращает (stats, error_message).
    """
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
        except Exception as e:
            logger.exception("Полный sync после изменения сервера завершился ошибкой: %s", e)
            return None, str(e)

    if not sub:
        return None, "subscription_manager unavailable"
    try:
        stats = await sub.sync_servers_with_config(auto_create_clients=True)
        return stats, None
    except Exception as e:
        logger.exception("sync_servers_with_config после изменения сервера: %s", e)
        return None, str(e)


async def _reload_and_sync_serialized(need_sync: bool) -> tuple[dict | None, str | None, bool]:
    """
    Последовательно выполняет reload server_manager и (опционально) sync,
    чтобы избежать гонок между параллельными CRUD-запросами админки.
    Возвращает (sync_stats, sync_error, sync_debounced).
    """
    async with _SERVER_CONFIG_OP_LOCK:
        try:
            await _reload_server_manager()
        except Exception as mgr_e:
            logger.error("Ошибка обновления менеджера серверов: %s", mgr_e)

        if not need_sync:
            return None, None, False

        sync_stats, sync_error = await _run_sync_servers_with_config()
        return sync_stats, sync_error, False


def create_blueprint(bot_app):
    bp = Blueprint("admin_servers", __name__)

    @bp.route("/api/admin/server-groups", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_server_groups(request, admin_id):
        data = await request.get_json(silent=True) or {}
        action = data.get("action", "list")
        if action == "list":
            groups = await get_server_groups(only_active=False)
            stats = await get_group_load_statistics()
            return jsonify({"success": True, "groups": groups, "stats": stats}), 200, _cors_headers()
        elif action == "add":
            name = data.get("name")
            description = data.get("description")
            is_default = data.get("is_default", False)
            if not name:
                return jsonify({"error": "Name is required"}), 400, _cors_headers()
            group_id = await add_server_group(name, description, is_default)
            return jsonify({"success": True, "group_id": group_id}), 200, _cors_headers()
        return jsonify({"error": "Invalid action"}), 400, _cors_headers()

    @bp.route("/api/admin/server-group/update", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_server_group_update(request, admin_id):
        data = await request.get_json(silent=True) or {}
        group_id = data.get("id")
        if not group_id:
            return jsonify({"error": "Group ID is required"}), 400, _cors_headers()
        await update_server_group(
            group_id,
            name=data.get("name"),
            description=data.get("description"),
            is_active=data.get("is_active"),
            is_default=data.get("is_default"),
        )
        return jsonify({"success": True}), 200, _cors_headers()

    @bp.route("/api/admin/servers-config", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_servers_config(request, admin_id):
        data = await request.get_json(silent=True) or {}
        action = data.get("action", "list")
        if action == "list":
            group_id = data.get("group_id")
            servers = await get_servers_config(group_id=group_id, only_active=False)
            return jsonify({"success": True, "servers": servers}), 200, _cors_headers()
        elif action == "add":
            group_id = data.get("group_id")
            name = data.get("name")
            host = data.get("host")
            login = data.get("login")
            password = data.get("password")
            if not all([group_id, name, host, login, password]):
                return jsonify({"error": "All fields are required"}), 400, _cors_headers()
            cf_norm, cf_err = normalize_client_flow_for_storage(data.get("client_flow"))
            if cf_err:
                return jsonify({"error": cf_err}), 400, _cors_headers()
            raw_active = data.get("is_active")
            insert_active = 1 if (raw_active is None or _coerce_server_active(raw_active)) else 0
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
            sync_stats, sync_error, sync_debounced = await _reload_and_sync_serialized(
                need_sync=(insert_active == 1)
            )
            payload = {"success": True, "server_id": server_id}
            if sync_stats is not None:
                payload["sync_stats"] = sync_stats
            if sync_error:
                payload["sync_error"] = sync_error
            if sync_debounced:
                payload["sync_debounced"] = True
            return jsonify(payload), 200, _cors_headers()
        elif action == "reorder":
            group_id = data.get("group_id")
            server_ids = data.get("server_ids")
            if group_id is None or not isinstance(server_ids, list) or len(server_ids) == 0:
                return jsonify({"error": "group_id and server_ids[] required"}), 400, _cors_headers()
            ok = await reorder_servers_in_group(int(group_id), server_ids)
            if not ok:
                return jsonify({"error": "Invalid order or group mismatch"}), 400, _cors_headers()
            await _reload_and_sync_serialized(need_sync=False)
            return jsonify({"success": True}), 200, _cors_headers()
        return jsonify({"error": "Invalid action"}), 400, _cors_headers()

    @bp.route("/api/admin/server-config/update", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_server_config_update(request, admin_id):
        data = await request.get_json(silent=True) or {}
        server_id = data.get("id")
        if not server_id:
            return jsonify({"error": "Server ID is required"}), 400, _cors_headers()
        update_data = {k: v for k, v in data.items() if k not in ("initData", "id")}
        if "client_flow" in update_data:
            cf_norm, cf_err = normalize_client_flow_for_storage(update_data.get("client_flow"))
            if cf_err:
                return jsonify({"error": cf_err}), 400, _cors_headers()
            update_data["client_flow"] = cf_norm
        old_server = await get_server_by_id(int(server_id))
        # Только если в запросе явно передан client_flow — иначе new_flow нельзя считать None
        # (частичный PATCH без поля не должен триггерить массовый sync и давать ложные сравнения).
        client_flow_changed = False
        if "client_flow" in update_data and old_server is not None:
            old_cf = ((old_server.get("client_flow") or "").strip() or None)
            new_cf = update_data["client_flow"]
            client_flow_changed = old_cf != new_cf
        await update_server_config(server_id, **update_data)
        sync_stats, sync_error, sync_debounced = await _reload_and_sync_serialized(
            need_sync=_was_inactive_and_now_active(old_server, update_data)
        )
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
        return jsonify(payload), 200, _cors_headers()

    @bp.route("/api/admin/server-config/sync-flow", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_server_config_sync_flow(request, admin_id):
        data = await request.get_json(silent=True) or {}
        server_id = data.get("server_id") or data.get("id")
        if not server_id:
            return jsonify({"error": "server_id is required"}), 400, _cors_headers()
        server = await get_server_by_id(int(server_id))
        if not server:
            return jsonify({"error": "Server not found"}), 404, _cors_headers()
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
        return jsonify({
            "success": True,
            "updated": updated,
            "skipped": skipped,
            "errors": errs[:20],
        }), 200, _cors_headers()

    @bp.route("/api/admin/server-config/delete", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_server_config_delete(request, admin_id):
        data = await request.get_json(silent=True) or {}
        server_id = data.get("id")
        if not server_id:
            return jsonify({"error": "Server ID is required"}), 400, _cors_headers()
        await delete_server_config(server_id)
        sync_stats, sync_error, sync_debounced = await _reload_and_sync_serialized(
            need_sync=True
        )
        payload = {"success": True}
        if sync_stats is not None:
            payload["sync_stats"] = sync_stats
        if sync_error:
            payload["sync_error"] = sync_error
        if sync_debounced:
            payload["sync_debounced"] = True
        return jsonify(payload), 200, _cors_headers()

    @bp.route("/api/admin/sync-all", methods=["POST", "OPTIONS"])
    @admin_route
    async def api_admin_sync_all(request, admin_id):
        sync_manager = get_ctx().sync_manager
        if not sync_manager:
            return jsonify({"error": "Sync manager not available"}), 503, _cors_headers()
        stats = await sync_manager.sync_all_subscriptions(auto_fix=True)
        return jsonify({"success": True, "stats": stats}), 200, _cors_headers()

    return bp
