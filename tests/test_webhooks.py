"""Crypto webhook: fixed HMAC vectors, replay idempotency, bad-signature 400 (§12)."""

import hashlib
import hmac
import json

from app.models import Order, PaymentEvent, Piece
from app.payments.crypto import verify_coinbase_signature

SECRET = "test-secret"


def _sign(raw: bytes, timestamp: str, secret: str = SECRET) -> str:
    return hmac.new(
        secret.encode(), timestamp.encode() + b"." + raw, hashlib.sha256
    ).hexdigest()


def test_known_hmac_vector():
    raw = b'{"id":"evt_1","type":"charge:confirmed","order_id":7}'
    ts = "1719000000"
    sig = _sign(raw, ts)
    assert verify_coinbase_signature(raw, ts, sig, SECRET) is True
    assert verify_coinbase_signature(raw, ts, sig, "wrong-secret") is False
    assert verify_coinbase_signature(raw, "1719000001", sig, SECRET) is False
    assert verify_coinbase_signature(b'{"id":"evt_1X"}', ts, sig, SECRET) is False


def _make_order(db):
    piece = Piece(title="T", pseudonym="p", price_cents=50000, status="published")
    db.add(piece)
    db.flush()
    order = Order(
        piece_id=piece.id,
        buyer_name="A",
        buyer_email="a@example.ca",
        status="awaiting_payment",
        method="crypto",
        amount_cents=50000,
        currency="CAD",
        reference_code="LV-ABCD",
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def _post(client, payload: dict, secret: str = SECRET, ts: str = "1719000000"):
    raw = json.dumps(payload).encode()
    # Sign the exact bytes we send.
    import httpx

    _ = httpx  # noqa: F841 (documents byte-exactness requirement)
    sig = _sign(raw, ts, secret)
    return client.post(
        "/webhooks/crypto",
        content=raw,
        headers={
            "content-type": "application/json",
            "x-cc-webhook-signature": sig,
            "x-cc-webhook-timestamp": ts,
        },
    ), raw


def test_confirmed_pays_replay_is_noop(client, db):
    order = _make_order(db)
    payload = {"id": "evt_replay_1", "type": "charge:confirmed", "order_id": order.id}
    res, _ = _post(client, payload)
    assert res.status_code == 200, res.text
    assert res.json()["order_status"] == "paid"

    db.refresh(order)
    assert order.status == "paid"
    assert db.get(Piece, order.piece_id).status == "sold"

    res2, _ = _post(client, payload)
    assert res2.status_code == 200
    assert res2.json()["status"] == "duplicate"
    events = db.query(PaymentEvent).filter_by(provider_event_id="evt_replay_1|charge:confirmed").all()
    assert len(events) == 1


def test_pending_does_not_pay(client, db):
    order = _make_order(db)
    res, _ = _post(
        client, {"id": "evt_pend_1", "type": "charge:pending", "order_id": order.id}
    )
    assert res.status_code == 200
    db.refresh(order)
    assert order.status == "awaiting_payment"


def test_invalid_signature_400_no_state_change(client, db):
    order = _make_order(db)
    payload = {"id": "evt_bad_1", "type": "charge:confirmed", "order_id": order.id}
    raw = json.dumps(payload).encode()
    res = client.post(
        "/webhooks/crypto",
        content=raw,
        headers={
            "content-type": "application/json",
            "x-cc-webhook-signature": "deadbeef",
            "x-cc-webhook-timestamp": "1719000000",
        },
    )
    assert res.status_code == 400
    db.refresh(order)
    assert order.status == "awaiting_payment"
    assert db.query(PaymentEvent).count() == 0
