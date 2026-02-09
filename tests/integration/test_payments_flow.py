"""Integration tests for payment webhook and successful payment flow."""
import datetime
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.db import (
    add_payment,
    add_server_config,
    add_server_group,
    get_all_subscriptions_by_user,
    get_or_create_subscriber,
    get_payment_by_id,
)
from bot.handlers.webhooks.payment_processors import process_payment_webhook
from bot.services.server_manager import MultiServerManager
from bot.services.subscription_manager import SubscriptionManager


@pytest.fixture
async def db_with_server(db):
    """DB with one server group and one server (required for create_subscription)."""
    suffix = uuid.uuid4().hex[:8]
    gid = await add_server_group(f"TestGroup_{suffix}", description="Test", is_default=True)
    await add_server_config(gid, f"test_srv_{suffix}", "https://example.com", "u", "p")
    yield


@pytest.fixture
def mock_bot_app():
    """Minimal bot app mock for payment_processors (send_message, etc.)."""
    app = MagicMock()
    app.bot = MagicMock()
    app.bot.send_message = AsyncMock()
    app.bot.edit_message_text = AsyncMock()
    return app


@pytest.fixture
def mock_managers():
    """Real SubscriptionManager with mock server_manager; ensure_client_on_server mocked."""
    server_manager = MagicMock(spec=MultiServerManager)
    sub_manager = SubscriptionManager(server_manager)
    # Avoid real X-UI calls; treat client as created
    sub_manager.ensure_client_on_server = AsyncMock(return_value=(True, True))
    sub_manager.attach_server_to_subscription = AsyncMock()
    return {
        "subscription_manager": sub_manager,
        "server_manager": server_manager,
        "notification_manager": MagicMock(),
    }


@pytest.mark.asyncio
async def test_process_payment_webhook_idempotent(db_with_server, mock_bot_app, mock_managers):
    """Calling process_payment_webhook twice with succeeded does not create duplicate subscription."""
    user_id = "web_idemuser"
    await get_or_create_subscriber(user_id)
    payment_id = "pay_idem_001"
    meta = {
        "type": "month",
        "device_limit": 1,
        "unique_email": "idem@test.com",
        "price": 100,
    }
    await add_payment(payment_id, user_id, "succeeded", meta=meta)

    with patch(
        "bot.handlers.webhooks.payment_processors.get_globals",
        return_value=mock_managers,
    ):
        await process_payment_webhook(mock_bot_app, payment_id, "succeeded")
        subs_after_first = await get_all_subscriptions_by_user(user_id, include_deleted=False)
        await process_payment_webhook(mock_bot_app, payment_id, "succeeded")
        subs_after_second = await get_all_subscriptions_by_user(user_id, include_deleted=False)

    assert len(subs_after_first) >= 1
    assert len(subs_after_second) == len(subs_after_first)


@pytest.mark.asyncio
async def test_process_payment_webhook_new_purchase_creates_subscription(
    db_with_server, mock_bot_app, mock_managers
):
    """process_payment_webhook with succeeded creates subscription and activates payment."""
    user_id = "web_newbuyer"
    await get_or_create_subscriber(user_id)
    payment_id = "pay_new_002"
    meta = {
        "type": "month",
        "device_limit": 1,
        "unique_email": "new@test.com",
        "price": 150,
    }
    await add_payment(payment_id, user_id, "succeeded", meta=meta)

    with patch(
        "bot.handlers.webhooks.payment_processors.get_globals",
        return_value=mock_managers,
    ):
        await process_payment_webhook(mock_bot_app, payment_id, "succeeded")

    payment = await get_payment_by_id(payment_id)
    assert payment is not None
    assert payment.get("activated") == 1

    subs = await get_all_subscriptions_by_user(user_id, include_deleted=False)
    assert len(subs) >= 1
    sub = subs[0]
    assert sub.get("status") == "active"
    now = int(datetime.datetime.now().timestamp())
    # expires_at roughly now + 30 days
    assert sub.get("expires_at", 0) > now
    assert sub.get("expires_at", 0) <= now + (35 * 24 * 60 * 60)
