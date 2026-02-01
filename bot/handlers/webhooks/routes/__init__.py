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


def register_all_blueprints(app, bot_app):
    """Register all blueprints in the correct order (specific routes before catch-all)."""
    app.register_blueprint(create_payment_blueprint(bot_app))
    app.register_blueprint(create_subscription_blueprint(bot_app))
    app.register_blueprint(create_api_public_blueprint(bot_app))
    app.register_blueprint(create_api_user_blueprint(bot_app))
    app.register_blueprint(create_api_auth_blueprint(bot_app))
    app.register_blueprint(create_api_admin_blueprint(bot_app))
    try:
        from bot.events import EVENTS_MODULE_ENABLED
        if EVENTS_MODULE_ENABLED:
            from bot.events.api import create_events_blueprint
            app.register_blueprint(create_events_blueprint())
    except ImportError:
        pass
    app.register_blueprint(static_bp)
