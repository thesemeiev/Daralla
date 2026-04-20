"""Unit tests for subscription helpers (is_subscription_active)."""
import time

import pytest

from daralla_backend.db.subscriptions_db import is_subscription_active


def test_is_subscription_active_true():
    """status=active and expires_at in future -> True."""
    now = int(time.time())
    sub = {"status": "active", "expires_at": now + 86400}
    assert is_subscription_active(sub) is True


def test_is_subscription_active_expired():
    """status=active but expires_at in past -> False."""
    now = int(time.time())
    sub = {"status": "active", "expires_at": now - 1}
    assert is_subscription_active(sub) is False


def test_is_subscription_active_deleted():
    """status=deleted -> False regardless of expires_at."""
    now = int(time.time())
    sub = {"status": "deleted", "expires_at": now + 86400}
    assert is_subscription_active(sub) is False


def test_is_subscription_active_status_expired():
    """status=expired -> False (expires_at in past)."""
    now = int(time.time())
    sub = {"status": "expired", "expires_at": now - 1}
    assert is_subscription_active(sub) is False
