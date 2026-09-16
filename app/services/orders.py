"""Order state machine + reference codes + TTL sweep (§7).

All status mutations go through `transition()`. Entering `paid` flips
the piece to `sold`.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from app.config import settings
from app.models import Order, Piece

# Charset without 0/O/1/I — readable over the phone at handover.
REF_CHARSET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

TRANSITIONS: dict[tuple[str, str], str] = {
    ("created", "provider_ready"): "awaiting_payment",
    ("created", "reserve_on_delivery"): "reserved",
    ("awaiting_payment", "payment_confirmed"): "paid",
    ("reserved", "payment_confirmed"): "paid",
    ("paid", "handover_scheduled"): "handover_scheduled",
    ("handover_scheduled", "handover_done"): "completed",
    ("awaiting_payment", "ttl_expired"): "cancelled",
    ("reserved", "ttl_expired"): "cancelled",
    ("awaiting_payment", "cancelled"): "cancelled",
    ("reserved", "cancelled"): "cancelled",
    ("paid", "refund_issued"): "refunded",
}


class IllegalTransition(ValueError):
    pass


def transition(order: Order, event: str, piece: Piece | None = None) -> str:
    """Apply `event` to `order`, returning the new status.

    Raises IllegalTransition when the (status, event) pair is not allowed.
    """
    key = (order.status, event)
    if key not in TRANSITIONS:
        raise IllegalTransition(f"Cannot apply {event!r} to order in {order.status!r}.")
    order.status = TRANSITIONS[key]
    now = datetime.now(timezone.utc)
    if order.status == "paid":
        order.paid_at = now
        if piece is not None:
            piece.status = "sold"
    elif order.status == "completed":
        order.completed_at = now
    return order.status


def generate_reference_code() -> str:
    suffix = "".join(secrets.choice(REF_CHARSET) for _ in range(4))
    return f"LV-{suffix}"


def is_reference_code(value: str) -> bool:
    if not value.startswith("LV-") or len(value) != 7:
        return False
    return all(c in REF_CHARSET for c in value[3:])


def sweep_expired(orders: list[Order], piece_lookup) -> int:
    """Cancel unpaid orders past expiry. Returns the count cancelled."""
    now = datetime.now(timezone.utc)
    count = 0
    for order in orders:
        if order.status not in ("awaiting_payment", "reserved"):
            continue
        expires = order.expires_at
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires is not None and expires <= now:
            transition(order, "ttl_expired", piece_lookup(order))
            count += 1
    return count


def ttl_hours() -> int:
    return settings.ORDER_TTL_HOURS
