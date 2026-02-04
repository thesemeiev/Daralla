"""
Пакет админ-маршрутов: единая точка входа для /api/admin/*.
"""
from flask import Blueprint

from . import auth, broadcast, servers, stats, subscription, users


def create_blueprint(bot_app):
    bp = Blueprint("api_admin", __name__)
    auth.register_auth_routes(bp)
    users.register_users_routes(bp)
    subscription.register_subscription_routes(bp)
    stats.register_stats_routes(bp)
    broadcast.register_broadcast_routes(bp, bot_app)
    servers.register_servers_routes(bp)
    return bp
