"""M3 — PayPal sandbox road: order, return, verified webhook (provider stubbed)."""

import json

import pytest

from app.models import Order, PaymentEvent, Piece
from app.payments import paypal as paypal_provider


@pytest.fixture()
def wall_piece(db, founder):
    piece = Piece(
        seller_user_id=founder.id,
        pseudonym="atelier nord",
        title="Veste de minuit",
        year=2024,
        textile="Wool twill",
        price_cents=390000,
        status="published",
    )
    db.add(piece)
    db.commit()
    db.refresh(piece)
    return piece


@pytest.fixture()
def paypal_stub(monkeypatch):
    monkeypatch.setattr(
        paypal_provider, "create_order",
        lambda **kw: {
            "provider_ref": "PAYPAL-ORDER-1",
            "approval_url": "https://www.sandbox.paypal.com/checkoutnow?token=PAYPAL-ORDER-1",
        },
    )
    monkeypatch.setattr(
        paypal_provider, "capture_order",
        lambda ref: {"captured": True, "status": "COMPLETED"},
    )
    monkeypatch.setattr(
        paypal_provider, "verify_webhook_signature", lambda headers, raw: True
    )


def buy_paypal(client, piece_id):
    return client.post("/api/orders", json={
        "piece_id": piece_id,
        "method": "paypal",
        "buyer_name": "Acheteuse",
        "buyer_email": "a@example.ca",
    })


def webhook(client, payload: dict):
    return client.post("/webhooks/paypal", content=json.dumps(payload).encode(), headers={
        "content-type": "application/json",
        "paypal-transmission-id": "t1",
        "paypal-transmission-sig": "s1",
    })


def test_paypal_order_returns_approval_road(client, wall_piece, db, paypal_stub):
    res = buy_paypal(client, wall_piece.id)
    assert res.status_code == 201, res.text
    order = res.json()
    assert order["status"] == "awaiting_payment"
    assert order["approval_url"].startswith("https://www.sandbox.paypal.com/")
    assert db.get(Order, order["id"]).provider_ref == "PAYPAL-ORDER-1"
    # Held like any unpaid commission.
    res2 = client.post("/api/orders", json={
        "piece_id": wall_piece.id, "method": "interac",
        "buyer_name": "B", "buyer_email": "b@example.ca",
    })
    assert res2.status_code == 409


def test_return_captures_but_webhook_confirms(client, wall_piece, db, paypal_stub):
    order = buy_paypal(client, wall_piece.id).json()
    ret = client.post(f"/api/orders/{order['id']}/paypal/return")
    assert ret.status_code == 200
    assert ret.json()["captured"] is True
    # Authoritative word still belongs to the webhook.
    assert ret.json()["order_status"] == "awaiting_payment"
    assert db.get(Order, order["id"]).status == "awaiting_payment"


def test_webhook_completed_pays_and_replay_is_noop(client, wall_piece, db, paypal_stub):
    order = buy_paypal(client, wall_piece.id).json()
    payload = {
        "id": "WH-PAYPAL-1",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {"id": "CAPTURE-1", "custom_id": order["reference_code"]},
    }
    res = webhook(client, payload)
    assert res.status_code == 200, res.text
    assert res.json()["order_status"] == "paid"
    assert db.get(Order, order["id"]).status == "paid"
    assert db.get(Piece, wall_piece.id).status == "sold"

    again = webhook(client, payload)
    assert again.json()["status"] == "duplicate"
    events = db.query(PaymentEvent).filter_by(provider_event_id="WH-PAYPAL-1").all()
    assert len(events) == 1


def test_webhook_matches_by_paypal_order_id(client, wall_piece, db, paypal_stub):
    order = buy_paypal(client, wall_piece.id).json()
    payload = {
        "id": "WH-PAYPAL-2",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {
            "id": "CAPTURE-2",
            "supplementary_data": {"related_ids": {"order_id": "PAYPAL-ORDER-1"}},
        },
    }
    res = webhook(client, payload)
    assert res.json()["order_status"] == "paid"


def test_webhook_other_events_record_without_paying(client, wall_piece, db, paypal_stub):
    order = buy_paypal(client, wall_piece.id).json()
    res = webhook(client, {
        "id": "WH-PAYPAL-3",
        "event_type": "PAYMENT.CAPTURE.DENIED",
        "resource": {"id": "CAPTURE-3", "custom_id": order["reference_code"]},
    })
    assert res.json()["order_status"] == "awaiting_payment"
    assert db.get(Order, order["id"]).status == "awaiting_payment"


def test_webhook_bad_signature_and_unknown_order(client, wall_piece, db, paypal_stub, monkeypatch):
    order = buy_paypal(client, wall_piece.id).json()
    monkeypatch.setattr(
        paypal_provider, "verify_webhook_signature", lambda headers, raw: False
    )
    res = webhook(client, {
        "id": "WH-PAYPAL-4",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {"id": "CAPTURE-4", "custom_id": order["reference_code"]},
    })
    assert res.status_code == 400
    assert db.get(Order, order["id"]).status == "awaiting_payment"
    assert db.query(PaymentEvent).count() == 0

    monkeypatch.setattr(
        paypal_provider, "verify_webhook_signature", lambda headers, raw: True
    )
    res = webhook(client, {
        "id": "WH-PAYPAL-5",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {"id": "CAPTURE-5", "custom_id": "LV-ZZZZ"},
    })
    assert res.status_code == 404


def test_return_refuses_non_paypal(client, wall_piece, db):
    res = client.post("/api/orders", json={
        "piece_id": wall_piece.id, "method": "interac",
        "buyer_name": "A", "buyer_email": "a@example.ca",
    })
    assert client.post(f"/api/orders/{res.json()['id']}/paypal/return").status_code == 404
