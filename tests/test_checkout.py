"""M2 — a full offline purchase: hold, status page, TTL, studio desk."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Order, Piece
from app.services.orders import sweep_expired


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


def buy(client, piece_id, method="interac", **over):
    body = {
        "piece_id": piece_id,
        "method": method,
        "buyer_name": "Acheteuse",
        "buyer_email": "a@example.ca",
        "buyer_phone": "514-555-0100",
        "handover_area": "Mile End",
        "handover_window": "Saturday, late morning",
    }
    body.update(over)
    return client.post("/api/orders", json=body)


def test_interac_order_holds_the_piece(client, wall_piece):
    res = buy(client, wall_piece.id)
    assert res.status_code == 201, res.text
    order = res.json()
    assert order["status"] == "awaiting_payment"
    assert order["method"] == "interac"
    assert order["amount_cents"] == 390000
    assert isinstance(order["amount_cents"], int)
    assert order["reference_code"].startswith("LV-")
    assert order["reference_code"] in order["instructions"]
    # Held against other buyers: a second commission is refused…
    res2 = buy(client, wall_piece.id, buyer_email="b@example.ca")
    assert res2.status_code == 409
    # …and the piece leaves the wall until the hold lifts.
    assert all(p["id"] != wall_piece.id for p in client.get("/api/pieces").json())
    assert client.get(f"/api/pieces/{wall_piece.id}").status_code == 404


def test_on_delivery_reserves_with_meeting(client, wall_piece):
    res = buy(client, wall_piece.id, method="on_delivery")
    assert res.status_code == 201, res.text
    order = res.json()
    assert order["status"] == "reserved"
    assert order["handover_area"] == "Mile End"
    assert order["instructions"] is not None


def test_status_page_guards_with_reference(client, wall_piece):
    order = buy(client, wall_piece.id).json()
    ok = client.get(f"/api/orders/{order['id']}?code={order['reference_code']}")
    assert ok.status_code == 200
    assert ok.json()["piece_title"] == "Veste de minuit"
    assert client.get(f"/api/orders/{order['id']}?code=LV-XXXX").status_code == 404
    assert client.get(f"/api/orders/{order['id']}").status_code == 404
    assert client.get(f"/api/orders/999999?code={order['reference_code']}").status_code == 404


def test_checkout_validation(client, wall_piece, db):
    assert buy(client, wall_piece.id, method="pigeon").status_code == 400
    assert buy(client, wall_piece.id, buyer_name="").status_code == 400
    assert buy(client, wall_piece.id, buyer_email="not-an-address").status_code == 400
    assert buy(client, wall_piece.id, method="on_delivery", handover_area="").status_code == 400
    wall_piece.status = "draft"
    db.commit()
    assert buy(client, wall_piece.id).status_code == 404


def test_studio_desk_full_passage(client, auth_headers, wall_piece, db):
    assert client.get("/api/studio/orders").status_code == 401
    order = buy(client, wall_piece.id).json()
    oid = order["id"]

    desk = client.get("/api/studio/orders", headers=auth_headers).json()
    assert desk[0]["reference_code"] == order["reference_code"]
    assert desk[0]["buyer_email"] == "a@example.ca"

    paid = client.post(f"/api/studio/orders/{oid}/mark-paid", headers=auth_headers)
    assert paid.status_code == 200
    assert paid.json()["status"] == "paid"
    assert db.get(Piece, wall_piece.id).status == "sold"
    # Settled commissions cannot be marked paid twice…
    assert client.post(f"/api/studio/orders/{oid}/mark-paid", headers=auth_headers).status_code == 400
    # …nor released.
    assert client.post(f"/api/studio/orders/{oid}/cancel", headers=auth_headers).status_code == 400

    sched = client.post(
        f"/api/studio/orders/{oid}/schedule", headers=auth_headers,
        json={"handover_window": "Saturday, late morning", "handover_place_note": "the café on Fairmount"},
    )
    assert sched.status_code == 200
    assert sched.json()["status"] == "handover_scheduled"
    assert sched.json()["handover_place_note"] == "the café on Fairmount"

    done = client.post(f"/api/studio/orders/{oid}/complete", headers=auth_headers)
    assert done.json()["status"] == "completed"


def test_status_page_names_the_hour_and_place(client, auth_headers, wall_piece):
    order = buy(client, wall_piece.id).json()
    oid = order["id"]
    client.post(f"/api/studio/orders/{oid}/mark-paid", headers=auth_headers)
    client.post(
        f"/api/studio/orders/{oid}/schedule", headers=auth_headers,
        json={"handover_window": "Saturday, late morning", "handover_place_note": "the café on Fairmount"},
    )
    status = client.get(f"/api/orders/{oid}?code={order['reference_code']}").json()
    assert status["status"] == "handover_scheduled"
    assert status["handover_window"] == "Saturday, late morning"
    assert status["handover_place_note"] == "the café on Fairmount"


def test_studio_cancel_releases_the_hold(client, auth_headers, wall_piece, db):
    order = buy(client, wall_piece.id, method="on_delivery").json()
    res = client.post(f"/api/studio/orders/{order['id']}/cancel", headers=auth_headers)
    assert res.json()["status"] == "cancelled"
    # The wall welcomes it back.
    assert buy(client, wall_piece.id, buyer_email="b@example.ca").status_code == 201


def test_ttl_expiry_releases_the_hold(client, wall_piece, db):
    order = buy(client, wall_piece.id).json()
    row = db.get(Order, order["id"])
    row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    assert sweep_expired([row], lambda o: db.get(Piece, o.piece_id)) == 1
    db.commit()
    assert db.get(Order, order["id"]).status == "cancelled"
    assert buy(client, wall_piece.id, buyer_email="b@example.ca").status_code == 201
