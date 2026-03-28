"""Integration tests for bot.db.users_db."""
import time
import uuid

import pytest

from bot.db import (
    add_payment,
    add_server_config,
    add_server_group,
    create_subscription,
    create_telegram_link,
    get_all_subscriptions_by_user,
    get_or_create_subscriber,
    get_user_by_auth_token,
    get_user_by_telegram_id_v2,
    get_user_by_id,
    merge_user_into_target,
    register_web_user,
    UsernameAlreadyExistsError,
    update_user_auth_token,
)


@pytest.mark.asyncio
async def test_get_user_by_auth_token_found(db):
    """get_user_by_auth_token returns user when token exists."""
    user_id = await register_web_user("testuser", "hash123")
    await update_user_auth_token(user_id, "secret_token_xyz")
    user = await get_user_by_auth_token("secret_token_xyz")
    assert user is not None
    assert user["user_id"] == user_id
    assert user["auth_token"] == "secret_token_xyz"


@pytest.mark.asyncio
async def test_get_user_by_auth_token_not_found(db):
    """get_user_by_auth_token returns None for unknown token."""
    await register_web_user("otheruser", "hash456")
    user = await get_user_by_auth_token("wrong_token")
    assert user is None


@pytest.mark.asyncio
async def test_get_or_create_subscriber_idempotent(db):
    """get_or_create_subscriber returns same internal id on second call."""
    user_id = "tg_abc123def456"
    id1 = await get_or_create_subscriber(user_id)
    id2 = await get_or_create_subscriber(user_id)
    assert id1 == id2


@pytest.mark.asyncio
async def test_register_web_user_success(db):
    """register_web_user creates user and returns user_id в едином формате usr_xxx."""
    user_id = await register_web_user("newuser", "passhash")
    assert user_id.startswith("usr_")
    assert len(user_id) == 16  # usr_ + 12 hex


@pytest.mark.asyncio
async def test_register_web_user_duplicate_raises(db):
    """register_web_user raises when username already exists."""
    await register_web_user("dupuser", "hash1")
    with pytest.raises(UsernameAlreadyExistsError) as exc_info:
        await register_web_user("dupuser", "hash2")
    assert "уже существует" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_user_by_telegram_id_v2_via_links(db):
    """get_user_by_telegram_id_v2 returns user when telegram_links exists."""
    user_id = await register_web_user("linkuser", "hash")
    await create_telegram_link("999888777", user_id)
    user = await get_user_by_telegram_id_v2("999888777", use_fallback=False)
    assert user is not None
    assert user["user_id"] == user_id


@pytest.mark.asyncio
async def test_get_user_by_telegram_id_v2_unknown_none(db):
    """get_user_by_telegram_id_v2 returns None for unknown telegram_id when no fallback."""
    user = await get_user_by_telegram_id_v2("000000000", use_fallback=False)
    assert user is None


@pytest.mark.asyncio
async def test_merge_user_into_target(db):
    """merge_user_into_target moves subscriptions and payments to target and deletes source."""
    suffix = uuid.uuid4().hex[:8]
    gid = await add_server_group(f"MergeGroup_{suffix}", description="Test", is_default=True)
    await add_server_config(gid, f"merge_srv_{suffix}", "https://example.com", "u", "p")

    source_user_id = "web_source_merge"
    target_user_id = "web_target_merge"
    source_internal_id = await get_or_create_subscriber(source_user_id)
    await get_or_create_subscriber(target_user_id)

    now = int(time.time())
    sub_id, _ = await create_subscription(
        subscriber_id=source_internal_id,
        period="month",
        device_limit=1,
        price=100.0,
        expires_at=now + 86400,
        group_id=gid,
    )
    await add_payment("pay_merge_001", source_user_id, "succeeded", {"type": "month"})

    result = await merge_user_into_target(source_user_id, target_user_id)
    assert result is True

    target_subs = await get_all_subscriptions_by_user(target_user_id, include_deleted=False)
    assert len(target_subs) >= 1
    assert await get_user_by_id(source_user_id) is None
