"""
Quart application for HTTP API and webhooks (заменяет прежнее Flask webhook app).
Создаёт Quart app, /health и регистрирует все blueprints (payment, subscription, api_*, admin*, events*, static).
"""

import logging
import os
import sqlite3

from quart import Quart, jsonify

from daralla_backend.db import DB_PATH
from daralla_backend.web.observability import get_metrics_snapshot, install_observability_hooks

logger = logging.getLogger(__name__)


def create_quart_app(bot_app=None) -> Quart:
    """Создаёт Quart-приложение для HTTP API и webhook'ов (payment, subscription, api, admin, events, static)."""
    app = Quart(__name__)
    install_observability_hooks(app, logger)

    @app.route("/health", methods=["GET"])
    async def health() -> tuple[dict, int]:
        """Simple health-check endpoint for load balancers / monitors."""
        return {"status": "ok"}, 200

    @app.route("/ready", methods=["GET"])
    async def ready() -> tuple[dict, int]:
        """Readiness probe: verify DB accessibility and optional bot context."""
        checks = {
            "db": "unknown",
            "context": "not_required" if bot_app is None else "unknown",
        }
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("SELECT 1")
            checks["db"] = "ok"
        except Exception:
            checks["db"] = "error"

        if bot_app is not None:
            try:
                from daralla_backend.app_context import get_ctx

                ctx = get_ctx()
                checks["context"] = (
                    "ok"
                    if ctx.server_manager and ctx.subscription_manager and ctx.sync_manager
                    else "degraded"
                )
            except Exception:
                checks["context"] = "error"

        is_ready = checks["db"] == "ok" and checks["context"] in ("ok", "not_required", "degraded")
        return {"status": "ok" if is_ready else "error", "checks": checks}, (200 if is_ready else 503)

    @app.route("/metrics", methods=["GET"])
    async def metrics() -> tuple[dict, int]:
        """JSON metrics endpoint for lightweight monitoring."""
        return {"metrics": get_metrics_snapshot()}, 200

    # Optionally register all existing blueprints. Use skip_subscription=True
    # so the async subscription blueprint (subscription) is used instead.
    if bot_app is not None:
        try:
            from daralla_backend.web.routes import create_subscription_blueprint
            from daralla_backend.web.routes.api_auth import create_blueprint as create_api_auth_blueprint
            from daralla_backend.web.routes.api_user import create_blueprint as create_api_user_blueprint
            from daralla_backend.web.routes.payment import create_blueprint as create_payment_blueprint
            from daralla_backend.web.routes.api_public import create_blueprint as create_api_public_blueprint
            from daralla_backend.web.routes.static import bp as static_bp
            from daralla_backend.web.routes.admin_check import create_blueprint as create_admin_check_blueprint
            from daralla_backend.web.routes.admin_users import create_blueprint as create_admin_users_blueprint
            from daralla_backend.web.routes.admin_subscriptions import create_blueprint as create_admin_subscriptions_blueprint
            from daralla_backend.web.routes.admin_stats import create_blueprint as create_admin_stats_blueprint
            from daralla_backend.web.routes.admin_charts import create_blueprint as create_admin_charts_blueprint
            from daralla_backend.web.routes.admin_broadcast import create_blueprint as create_admin_broadcast_blueprint
            from daralla_backend.web.routes.admin_servers import create_blueprint as create_admin_servers_blueprint
            from daralla_backend.web.routes.admin_notifications import create_blueprint as create_admin_notifications_blueprint
            from daralla_backend.web.routes.admin_commerce import create_blueprint as create_admin_commerce_blueprint

            app.register_blueprint(create_payment_blueprint(bot_app))
            try:
                from daralla_backend.events import EVENTS_MODULE_ENABLED
                if EVENTS_MODULE_ENABLED:
                    from daralla_backend.web.routes.events import create_blueprint as create_events_blueprint
                    app.register_blueprint(create_events_blueprint())
            except ImportError:
                pass
            app.register_blueprint(create_subscription_blueprint(bot_app))
            app.register_blueprint(create_api_public_blueprint(bot_app))
            app.register_blueprint(create_api_auth_blueprint(bot_app))
            app.register_blueprint(create_api_user_blueprint(bot_app))
            app.register_blueprint(create_admin_check_blueprint(bot_app))
            app.register_blueprint(create_admin_users_blueprint(bot_app))
            app.register_blueprint(create_admin_subscriptions_blueprint(bot_app))
            app.register_blueprint(create_admin_stats_blueprint(bot_app))
            app.register_blueprint(create_admin_charts_blueprint(bot_app))
            app.register_blueprint(create_admin_broadcast_blueprint(bot_app))
            app.register_blueprint(create_admin_servers_blueprint(bot_app))
            app.register_blueprint(create_admin_notifications_blueprint(bot_app))
            app.register_blueprint(create_admin_commerce_blueprint(bot_app))
            app.register_blueprint(static_bp)
            logger.info(
                "Registered webhook blueprints on Quart app "
                "(payment, subscription, api_public, api_auth, api_user, admin*, events*, static=async)"
            )
        except Exception as e:  # pragma: no cover - defensive logging
            logger.error("Failed to register blueprints on Quart app: %s", e, exc_info=True)

    return app


if __name__ == "__main__":
    # Local development entrypoint:
    #   python -m daralla_backend.web.app_quart
    # This runs Quart with no `bot_app` integration (only /health and static routes
    # that do not depend on bot state). In production, prefer an ASGI server.
    logging.basicConfig(level=logging.INFO)
    port = int(os.getenv("PORT", "8080"))
    app = create_quart_app()
    app.run(host="0.0.0.0", port=port)

