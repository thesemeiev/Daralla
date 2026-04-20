"""Integration tests for daralla_backend.db.subscriptions_db."""
import time
import uuid

import pytest

from daralla_backend.db import (
    add_server_config,
    add_server_group,
    create_subscription,
    get_or_create_subscriber,
    get_subscription_by_id,
    get_subscription_by_token,
)


@pytest.fixture
async def db_with_server(db):
    """DB with one server group (create_subscription needs group_id or default group)."""
    suffix = uuid.uuid4().hex[:8]
    gid = await add_server_group(f"SubGroup_{suffix}", description="Test", is_default=True)
    await add_server_config(gid, f"srv_{suffix}", "https://example.com", "u", "p")
    yield


@pytest.mark.asyncio
@pytest.mark.usefixtures("db_with_server")
async def test_create_subscription_and_get_by_token():
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
@pytest.mark.usefixtures("db_with_server")
async def test_get_subscription_by_id_owner():
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
@pytest.mark.usefixtures("db_with_server")
async def test_get_subscription_by_id_other_user_none():
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
