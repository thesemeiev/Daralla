"""
Quart-native route blueprints (async handlers, no event-loop workarounds).
"""

from .subscription import create_subscription_blueprint

__all__ = ["create_subscription_blueprint"]
