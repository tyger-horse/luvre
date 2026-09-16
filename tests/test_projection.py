"""Blind-seller regression (§2.1). NEVER delete or skip this module.

The public API must never return seller email, seller id, or any seller
identity — only the piece's `pseudonym`.
"""

import json

import pytest

from app.schemas import PUBLIC_IMAGE_KEYS, PUBLIC_PIECE_KEYS

FORBIDDEN = ("seller_user_id", "seller", "email", "password_hash", "password")


def _assert_no_seller_keys(payload) -> None:
    text = json.dumps(payload).lower()
    for key in FORBIDDEN:
        assert f'"{key}"' not in text, f"seller identity leaked via {key!r}"


def test_list_projection_exact_keys(client, published_piece):
    res = client.get("/api/pieces")
    assert res.status_code == 200, res.text
    items = res.json()
    assert len(items) == 1
    piece = items[0]
    assert set(piece.keys()) == set(PUBLIC_PIECE_KEYS)
    assert set(piece["images"][0].keys()) == set(PUBLIC_IMAGE_KEYS)
    _assert_no_seller_keys(items)


def test_detail_projection_hides_seller(client, published_piece):
    res = client.get(f"/api/pieces/{published_piece.id}")
    assert res.status_code == 200, res.text
    piece = res.json()
    assert set(piece.keys()) == set(PUBLIC_PIECE_KEYS)
    assert piece["pseudonym"] == "atelier nord"
    assert piece["price_cents"] == 390000
    assert isinstance(piece["price_cents"], int)
    _assert_no_seller_keys(piece)


def test_sold_status_projects_but_never_drafts(client, db, published_piece):
    published_piece.status = "sold"
    db.commit()
    res = client.get(f"/api/pieces/{published_piece.id}")
    assert res.status_code == 200
    assert res.json()["status"] == "sold"
    assert set(res.json().keys()) == set(PUBLIC_PIECE_KEYS)


def test_drafts_invisible_publicly(client, db, published_piece):
    from app.models import Piece

    draft = Piece(
        seller_user_id=None,
        pseudonym="secret",
        title="Unseen",
        price_cents=100,
        status="draft",
    )
    db.add(draft)
    db.commit()
    res = client.get("/api/pieces")
    titles = [p["title"] for p in res.json()]
    assert "Unseen" not in titles
    assert client.get(f"/api/pieces/{draft.id}").status_code == 404


def test_studio_desk_open_without_accounts(client):
    # No accounts: the knock is the only door. The desk answers directly.
    assert client.get("/api/studio/orders").status_code == 200
    assert client.get("/api/studio/pieces").status_code == 200
    res = client.post("/api/pieces", json={"title": "X"})
    assert res.status_code == 201
