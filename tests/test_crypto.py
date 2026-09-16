"""Manual crypto: buyer sends to the wallet, pastes the tx hash as proof."""

import pytest

from app.config import settings
from app.models import Order, Piece


@pytest.fixture()
def wall_piece(db):
    piece = Piece(
        seller_user_id=None,
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
def wallet(monkeypatch):
    addrs = {
        "CRYPTO_ETH_ADDRESS": "0xF0EdE6aCCc101ba707ca7e7d0D12dBFBb2D9C1ba",
        "CRYPTO_BTC_ADDRESS": "bc1q392r4qk948zj4ayun4x9hrfrfe2mk8mnhfgswwfhu4vq5hmtl6asn6xs2y",
        "CRYPTO_USDC_ADDRESS": "0xF0EdE6aCCc101ba707ca7e7d0D12dBFBb2D9C1ba",
    }
    for key, value in addrs.items():
        monkeypatch.setattr(settings, key, value)
    return addrs


def buy_crypto(client, piece_id, coin="btc"):
    return client.post("/api/orders", json={
        "piece_id": piece_id,
        "method": "crypto",
        "buyer_name": "Acheteuse",
        "buyer_email": "a@example.ca",
        "pay_currency": coin,
    })


def test_crypto_order_names_the_wallet(client, wall_piece, db, wallet):
    res = buy_crypto(client, wall_piece.id)
    assert res.status_code == 201, res.text
    order = res.json()
    assert order["status"] == "awaiting_payment"
    assert order["pay_currency"] == "btc"
    assert order["checkout_url"] is None
    assert wallet["CRYPTO_BTC_ADDRESS"] in (order["instructions"] or "")
    assert "Bitcoin" in (order["instructions"] or "")
    assert order["reference_code"] in (order["instructions"] or "")
    assert db.get(Order, order["id"]).provider_ref is None

    eth = buy_crypto(client, wall_piece.id, coin="eth")
    assert eth.status_code == 409  # held, whichever coin


def test_crypto_needs_a_coin(client, wall_piece):
    res = client.post("/api/orders", json={
        "piece_id": wall_piece.id, "method": "crypto",
        "buyer_name": "A", "buyer_email": "a@example.ca",
        "pay_currency": "doge",
    })
    assert res.status_code == 400
    res = client.post("/api/orders", json={
        "piece_id": wall_piece.id, "method": "crypto",
        "buyer_name": "A", "buyer_email": "a@example.ca",
    })
    assert res.status_code == 400


def test_sent_proof_kept_then_desk_settles(client, auth_headers, wall_piece, db, wallet):
    order = buy_crypto(client, wall_piece.id).json()
    tx = "a" * 64

    sent = client.post(f"/api/orders/{order['id']}/tx-hash", json={
        "code": order["reference_code"], "tx_hash": tx,
    })
    assert sent.status_code == 200, sent.text
    assert sent.json()["tx_hash"] == tx
    assert "watching the chain" in (sent.json()["instructions"] or "")
    assert db.get(Order, order["id"]).status == "awaiting_payment"

    # The desk checks the chain with its own eyes, then marks paid.
    desk = client.get("/api/studio/orders", headers=auth_headers).json()
    assert desk[0]["tx_hash"] == tx
    paid = client.post(f"/api/studio/orders/{order['id']}/mark-paid", headers=auth_headers)
    assert paid.json()["status"] == "paid"
    assert db.get(Piece, wall_piece.id).status == "sold"


def test_proof_guards(client, wall_piece, db, wallet):
    order = buy_crypto(client, wall_piece.id).json()
    url = f"/api/orders/{order['id']}/tx-hash"
    assert client.post(url, json={"code": "LV-XXXX", "tx_hash": "b" * 64}).status_code == 404
    assert client.post(url, json={"code": order["reference_code"], "tx_hash": "short"}).status_code == 400
    assert client.post(url, json={"code": order["reference_code"], "tx_hash": "not a hash!!"}).status_code == 400
    assert db.get(Order, order["id"]).tx_hash is None

    interac = client.post("/api/orders", json={
        "piece_id": wall_piece.id, "method": "interac",
        "buyer_name": "B", "buyer_email": "b@example.ca",
    })
    assert interac.status_code == 409  # held by the crypto commission, proof or not
