import time

import pytest

from bot.db.payment_webhooks_db import begin_webhook_event


@pytest.mark.asyncio
async def test_begin_webhook_event_is_insert_first_idempotent(db):
    now_ts = int(time.time())
    first = await begin_webhook_event(
        event_key="yookassa:pay_1:succeeded",
        provider="yookassa",
        payment_id="pay_1",
        status="succeeded",
        now_ts=now_ts,
    )
    second = await begin_webhook_event(
        event_key="yookassa:pay_1:succeeded",
        provider="yookassa",
        payment_id="pay_1",
        status="succeeded",
        now_ts=now_ts,
    )
    assert first is True
    assert second is False
