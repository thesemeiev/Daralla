"""Service helpers for payment webhook routes."""

from __future__ import annotations

from bot.db import get_payment_by_id


async def resolve_payment_for_cryptocloud_raw_id(raw_id: str):
    """Resolve payment record by CryptoCloud raw id and normalized payment id."""
    payment_id = raw_id
    info = await get_payment_by_id(raw_id)
    if not info and not str(raw_id).strip().upper().startswith("INV-"):
        payment_id = "INV-" + str(raw_id).strip()
        info = await get_payment_by_id(payment_id)
    if info:
        payment_id = info["payment_id"]
    return payment_id, info
