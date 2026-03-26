"""Integration tests for bot.db.subscriptions_db."""
import time

import pytest

from bot.db import (
    create_subscription,
    get_or_create_subscriber,
    get_subscription_by_id,
    get_subscription_by_token,
)


@pytest.fixture
async def db_with_server(db):
    """Compatibility fixture for subscription tests."""
    yield


@pytest.mark.asyncio
async def test_create_subscription_and_get_by_token(db_with_server):
    """create_subscription returns (sub_id, token); get_subscription_by_token returns sub."""
    user_id = "web_subuser"
    subscriber_id = await get_or_create_subscriber(user_id)
    now = int(time.time())
    expires_at = now + 30 * 24 * 60 * 60
    sub_id, token = await create_subscription(
        subscriber_id=subscriber_id,
        period="month",
        device_limit=1,
        price=100.0,
        expires_at=expires_at,
        name="Test sub",
    )
    assert sub_id is not None
    assert isinstance(token, str) and len(token) > 0

    sub = await get_subscription_by_token(token)
    assert sub is not None
    assert sub["id"] == sub_id
    assert sub["subscription_token"] == token
    assert sub["subscriber_id"] == subscriber_id
    assert sub["status"] == "active"
    assert sub["expires_at"] == expires_at


@pytest.mark.asyncio
async def test_get_subscription_by_id_owner(db_with_server):
    """get_subscription_by_id returns sub for owner user_id."""
    user_id = "web_owner"
    subscriber_id = await get_or_create_subscriber(user_id)
    now = int(time.time())
    sub_id, token = await create_subscription(
        subscriber_id=subscriber_id,
        period="month",
        device_limit=1,
        price=50.0,
        expires_at=now + 86400,
    )
    sub = await get_subscription_by_id(sub_id, user_id)
    assert sub is not None
    assert sub["id"] == sub_id


@pytest.mark.asyncio
async def test_get_subscription_by_id_other_user_none(db_with_server):
    """get_subscription_by_id returns None for different user_id."""
    user_id = "web_owner2"
    other_user_id = "web_other"
    await get_or_create_subscriber(user_id)
    await get_or_create_subscriber(other_user_id)
    subscriber_id = await get_or_create_subscriber(user_id)
    now = int(time.time())
    sub_id, _ = await create_subscription(
        subscriber_id=subscriber_id,
        period="month",
        device_limit=1,
        price=50.0,
        expires_at=now + 86400,
    )
    sub = await get_subscription_by_id(sub_id, other_user_id)
    assert sub is None
