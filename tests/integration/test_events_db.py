"""Integration tests for events module: add_counted_payment, get_leaderboard."""
from datetime import datetime, timedelta, timezone

import pytest

from bot.db import get_or_create_subscriber
from bot.events.db.queries import (
    add_counted_payment,
    create_event,
    get_leaderboard,
    get_or_create_referral_code,
    list_events_active,
)


@pytest.fixture
async def db_with_event(db):
    """DB with one active event and referral codes for two users."""
    now = datetime.now(timezone.utc)
    start = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    await create_event("Test Event", "Test", start, end, rewards_json="[]", status="active")

    referrer_id = "usr_referrer001"
    await get_or_create_subscriber(referrer_id)
    await get_or_create_referral_code(referrer_id)

    yield


@pytest.mark.asyncio
async def test_add_counted_payment_and_leaderboard(db_with_event):
    """add_counted_payment adds record; get_leaderboard returns referrer with count."""
    active = await list_events_active()
    assert len(active) >= 1
    event_id = active[0]["id"]

    referrer_user_id = "usr_referrer001"
    payment_id = "pay_test_001"

    await add_counted_payment(event_id, referrer_user_id, payment_id)
    leaderboard = await get_leaderboard(event_id, limit=10)
    assert len(leaderboard) >= 1
    row = next(r for r in leaderboard if r["referrer_user_id"] == referrer_user_id)
    assert row["count"] == 1

    await add_counted_payment(event_id, referrer_user_id, "pay_test_002")
    leaderboard2 = await get_leaderboard(event_id, limit=10)
    row2 = next(r for r in leaderboard2 if r["referrer_user_id"] == referrer_user_id)
    assert row2["count"] == 2


@pytest.mark.asyncio
async def test_add_counted_payment_idempotent(db_with_event):
    """Same payment_id + event_id is idempotent (INSERT OR IGNORE)."""
    active = await list_events_active()
    assert len(active) >= 1
    event_id = active[0]["id"]
    referrer_user_id = "usr_referrer001"
    payment_id = "pay_idem_001"

    await add_counted_payment(event_id, referrer_user_id, payment_id)
    await add_counted_payment(event_id, referrer_user_id, payment_id)

    leaderboard = await get_leaderboard(event_id, limit=10)
    row = next((r for r in leaderboard if r["referrer_user_id"] == referrer_user_id), None)
    assert row is not None
    assert row["count"] == 1
