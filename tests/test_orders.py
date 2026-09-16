"""Order state machine, reference codes, TTL, sold flip (§7 + §12)."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Order, Piece
from app.services.orders import (
    IllegalTransition,
    REF_CHARSET,
    generate_reference_code,
    is_reference_code,
    sweep_expired,
    transition,
)


def _order(**kw):
    base = dict(
        piece_id=1,
        buyer_name="Acheteuse",
        buyer_email="a@example.ca",
        status="created",
        method="interac",
        amount_cents=390000,
        currency="CAD",
        reference_code=generate_reference_code(),
    )
    base.update(kw)
    return Order(**base)


def test_happy_paths():
    o = _order()
    assert transition(o, "provider_ready") == "awaiting_payment"
    assert transition(o, "payment_confirmed") == "paid"

    o2 = _order()
    assert transition(o2, "reserve_on_delivery") == "reserved"
    assert transition(o2, "payment_confirmed") == "paid"
    assert transition(o2, "handover_scheduled") == "handover_scheduled"
    assert transition(o2, "handover_done") == "completed"


def test_illegal_transitions_rejected():
    with pytest.raises(IllegalTransition):
        transition(_order(), "payment_confirmed")  # created -> paid skips ready
    with pytest.raises(IllegalTransition):
        transition(_order(status="awaiting_payment"), "handover_done")
    with pytest.raises(IllegalTransition):
        transition(_order(status="paid"), "ttl_expired")
    with pytest.raises(IllegalTransition):
        transition(_order(status="completed"), "refund_issued")


def test_reference_codes_charset_and_unique():
    codes = set()
    for _ in range(5000):
        codes.add(generate_reference_code())
        if len(codes) >= 300:
            break
    assert len(codes) >= 300  # generator has enough entropy to fill the set
    for code in codes:
        assert is_reference_code(code)
        assert len(code) == 7 and code.startswith("LV-")
        assert "0" not in code and "O" not in code
        assert "1" not in code and "I" not in code
        assert all(c in REF_CHARSET for c in code[3:])
    assert not is_reference_code("LV-01OI")
    assert not is_reference_code("nope")


def test_ttl_expiry_cancels_unpaid_only(db):
    now = datetime.now(timezone.utc)
    piece = Piece(title="T", pseudonym="p", price_cents=100, status="published")
    db.add(piece)
    db.flush()
    expired = _order(
        piece_id=piece.id, status="awaiting_payment",
        expires_at=now - timedelta(hours=1),
    )
    fresh = _order(
        piece_id=piece.id, status="awaiting_payment",
        expires_at=now + timedelta(hours=47),
        reference_code=generate_reference_code(),
    )
    paid = _order(
        piece_id=piece.id, status="paid",
        expires_at=now - timedelta(hours=1),
        reference_code=generate_reference_code(),
    )
    for o in (expired, fresh, paid):
        db.add(o)
    db.commit()
    n = sweep_expired([expired, fresh, paid], lambda o: db.get(Piece, o.piece_id))
    assert n == 1
    assert expired.status == "cancelled"
    assert fresh.status == "awaiting_payment"
    assert paid.status == "paid"


def test_entering_paid_marks_piece_sold():
    piece = Piece(title="T", pseudonym="p", price_cents=100, status="published")
    order = _order(status="awaiting_payment")
    transition(order, "payment_confirmed", piece)
    assert order.status == "paid"
    assert order.paid_at is not None
    assert piece.status == "sold"


def test_amounts_are_ints(client, published_piece):
    res = client.get(f"/api/pieces/{published_piece.id}")
    assert isinstance(res.json()["price_cents"], int)
    assert res.json()["price_cents"] == 390000
