"""M4 — crypto charges: hosted road, confirmed-only settlement (provider stubbed)."""

import hashlib
import hmac
import json

import pytest

from app.models import Order, PaymentEvent, Piece
from app.payments import crypto as crypto_provider


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
def charge_stub(monkeypatch):
    monkeypatch.setattr(
        crypto_provider, "create_charge",
        lambda **kw: {
            "provider_ref": "CHG-1",
            "checkout_url": "https://commerce.coinbase.com/charges/CHG-1",
        },
    )


def buy_crypto(client, piece_id):
    return client.post("/api/orders", json={
        "piece_id": piece_id,
        "method": "crypto",
        "buyer_name": "Acheteuse",
        "buyer_email": "a@example.ca",
    })


def coinbase_hook(client, payload: dict, secret: str = "test-secret", ts: str = "1719000000"):
    raw = json.dumps(payload).encode()
    sig = hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return client.post("/webhooks/crypto", content=raw, headers={
        "content-type": "application/json",
        "x-cc-webhook-signature": sig,
        "x-cc-webhook-timestamp": ts,
    })


def btpay_hook(client, payload: dict, monkeypatch, valid: bool = True):
    monkeypatch.setattr(
        crypto_provider, "verify_btpay_signature", lambda raw, sig, secret: valid
    )
    # The handler calls the module-global imported into app.main; patch there too.
    import app.main as main

    monkeypatch.setattr(main, "verify_btpay_signature", lambda raw, sig, secret: valid)
    return client.post("/webhooks/crypto", content=json.dumps(payload).encode(), headers={
        "content-type": "application/json",
        "btcpay-sig": "stubbed",
    })


def test_crypto_order_returns_hosted_road(client, wall_piece, db, charge_stub):
    res = buy_crypto(client, wall_piece.id)
    assert res.status_code == 201, res.text
    order = res.json()
    assert order["status"] == "awaiting_payment"
    assert order["checkout_url"] == "https://commerce.coinbase.com/charges/CHG-1"
    assert order["approval_url"] is None
    assert db.get(Order, order["id"]).provider_ref == "CHG-1"


def test_confirmed_settles_pending_only_settles_the_page(client, wall_piece, db, charge_stub):
    order = buy_crypto(client, wall_piece.id).json()

    pending = coinbase_hook(client, {
        "id": "evt_pend_9",
        "type": "charge:pending",
        "data": {"id": "CHG-1", "metadata": {"reference": order["reference_code"]}},
    })
    assert pending.status_code == 200
    assert db.get(Order, order["id"]).status == "awaiting_payment"
    status = client.get(f"/api/orders/{order['id']}?code={order['reference_code']}").json()
    assert "settling" in (status["instructions"] or "")

    confirmed = coinbase_hook(client, {
        "id": "evt_conf_9",
        "type": "charge:confirmed",
        "data": {"id": "CHG-1", "metadata": {"reference": order["reference_code"]}},
    })
    assert confirmed.json()["order_status"] == "paid"
    assert db.get(Order, order["id"]).status == "paid"
    assert db.get(Piece, wall_piece.id).status == "sold"

    again = coinbase_hook(client, {
        "id": "evt_conf_9",
        "type": "charge:confirmed",
        "data": {"id": "CHG-1", "metadata": {"reference": order["reference_code"]}},
    })
    assert again.json()["status"] == "duplicate"
    assert db.query(PaymentEvent).filter_by(provider_event_id="evt_conf_9|charge:confirmed").count() == 1


def test_charge_matched_by_provider_ref(client, wall_piece, db, charge_stub):
    order = buy_crypto(client, wall_piece.id).json()
    res = coinbase_hook(client, {
        "id": "evt_conf_10",
        "type": "charge:confirmed",
        "data": {"id": "CHG-1", "metadata": {}},
    })
    assert res.json()["order_status"] == "paid"


def test_bad_signature_changes_nothing(client, wall_piece, db, charge_stub):
    order = buy_crypto(client, wall_piece.id).json()
    res = coinbase_hook(
        client,
        {"id": "evt_bad_9", "type": "charge:confirmed",
         "data": {"id": "CHG-1", "metadata": {"reference": order["reference_code"]}}},
        secret="wrong-secret",
    )
    assert res.status_code == 400
    assert db.get(Order, order["id"]).status == "awaiting_payment"


def test_btcpay_settled_pays_received_only_notes(client, wall_piece, db, charge_stub, monkeypatch):
    order = buy_crypto(client, wall_piece.id).json()
    meta = {"orderId": str(order["id"]), "reference": order["reference_code"]}

    noted = btpay_hook(client, {
        "type": "InvoiceReceivedPayment", "invoiceId": "INV-1", "metadata": meta,
    }, monkeypatch)
    assert noted.status_code == 200
    assert db.get(Order, order["id"]).status == "awaiting_payment"

    settled = btpay_hook(client, {
        "type": "InvoiceSettled", "invoiceId": "INV-1", "metadata": meta,
    }, monkeypatch)
    assert settled.json()["order_status"] == "paid"
    assert db.get(Piece, wall_piece.id).status == "sold"

    refused = btpay_hook(client, {
        "type": "InvoiceSettled", "invoiceId": "INV-1", "metadata": meta,
    }, monkeypatch, valid=False)
    assert refused.status_code == 400
