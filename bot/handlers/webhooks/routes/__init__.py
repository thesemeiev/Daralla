"""
Register all webhook route blueprints with the Flask app.
Order: payment, subscription, api_public, api_user, api_auth, api_admin, [events], static.
"""
from .payment import create_blueprint as create_payment_blueprint
from .static import bp as static_bp
from .subscription import create_blueprint as create_subscription_blueprint
from .api_public import create_blueprint as create_api_public_blueprint
from .api_auth import create_blueprint as create_api_auth_blueprint
from .api_user import create_blueprint as create_api_user_blueprint
from .api_admin import create_blueprint as create_api_admin_blueprint


def register_all_blueprints(app, bot_app, skip_subscription=False, skip_api_auth=False, skip_api_user=False, skip_payment=False, skip_api_public=False, skip_api_admin=False, skip_static=False):
    """Register all blueprints in the correct order (specific routes before catch-all).
    If skip_*=True, that blueprint is not registered (for Quart app which registers its own async version)."""
    if not skip_payment:
        app.register_blueprint(create_payment_blueprint(bot_app))
    if not skip_subscription:
        app.register_blueprint(create_subscription_blueprint(bot_app))
    if not skip_api_public:
        app.register_blueprint(create_api_public_blueprint(bot_app))
    if not skip_api_user:
        app.register_blueprint(create_api_user_blueprint(bot_app))
    if not skip_api_auth:
        app.register_blueprint(create_api_auth_blueprint(bot_app))
    if not skip_api_admin:
        app.register_blueprint(create_api_admin_blueprint(bot_app))
    try:
        from bot.events import EVENTS_MODULE_ENABLED
        if EVENTS_MODULE_ENABLED:
            from bot.events.api import create_events_blueprint
            app.register_blueprint(create_events_blueprint())
    except ImportError:
        pass
    if not skip_static:
        app.register_blueprint(static_bp)
