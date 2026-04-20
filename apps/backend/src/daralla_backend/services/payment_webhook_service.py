"""Service helpers for payment webhook routes."""

from __future__ import annotations

import json

from daralla_backend.db import get_payment_by_id


def parse_yookassa_webhook_payload(data):
    """
    Parse YooKassa webhook payload and normalize to (payment_id, status).

    Returns tuple (payment_id, status) or None for ignorable events.
    Raises ValueError on invalid payload.
    """
    if not data or "object" not in data:
        raise ValueError("missing object")
    event = (data.get("event") or "").strip().lower()
    obj = data["object"]

    if event.startswith("refund."):
        if event != "refund.succeeded":
            return None
        payment_id = obj.get("payment_id")
        refund_status = (obj.get("status") or "").strip().lower()
        if not payment_id or not refund_status:
            raise ValueError("refund payload missing payment_id or status")
        if refund_status != "succeeded":
            return None
        return (payment_id, "refunded")

    if event and not event.startswith("payment."):
        return None

    payment_id = obj.get("id")
    status = obj.get("status")
    if not payment_id or not status:
        raise ValueError("payment payload missing id or status")
    return (payment_id, status)


def normalize_cryptocloud_payload(json_payload, form_payload):
    """
    Normalize CryptoCloud webhook payload from JSON or form.

    form_payload is expected to be mapping-like (e.g. MultiDict from Quart).
    """
    if json_payload:
        return json_payload
    if not form_payload:
        return None
    to_dict = getattr(form_payload, "to_dict", None)
    flat = to_dict() if callable(to_dict) else dict(form_payload)
    invoice_info = flat.get("invoice_info")
    if isinstance(invoice_info, str) and invoice_info.strip().startswith("{"):
        try:
            flat["invoice_info"] = json.loads(invoice_info)
        except (json.JSONDecodeError, TypeError):
            flat["invoice_info"] = {}
    elif "invoice_info" not in flat:
        flat["invoice_info"] = {}
    return flat


def map_cryptocloud_status(raw_status: str) -> str:
    status = (raw_status or "").strip().lower()
    if status == "success":
        return "succeeded"
    if status in ("cancelled", "canceled"):
        return "canceled"
    return "failed"


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


async def resolve_cryptocloud_postback_target(payload: dict):
    """Resolve processing target from normalized CryptoCloud payload."""
    status = (payload.get("status") or "").strip().lower()
    invoice_info = payload.get("invoice_info") or {}
    raw_id = invoice_info.get("uuid") or payload.get("invoice_id")
    if not raw_id:
        return None

    payment_id, info = await resolve_payment_for_cryptocloud_raw_id(raw_id)
    return {
        "status": status,
        "raw_id": raw_id,
        "payment_id": payment_id,
        "payment_found": bool(info),
        "mapped_status": map_cryptocloud_status(status),
    }
