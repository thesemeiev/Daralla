"""
Пакет админ-маршрутов: единая точка входа для /api/admin/*.
"""
from flask import Blueprint

from . import auth, broadcast, overview, servers, subscription, users


def create_blueprint(bot_app):
    bp = Blueprint("api_admin", __name__)
    auth.register_auth_routes(bp)
    users.register_users_routes(bp)
    subscription.register_subscription_routes(bp)
    overview.register_overview_routes(bp)
    broadcast.register_broadcast_routes(bp, bot_app)
    servers.register_servers_routes(bp)
    return bp
