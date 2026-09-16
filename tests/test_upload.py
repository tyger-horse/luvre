"""M1 revised — upload JPEG → cover-cropped plate + palette, hung at once."""

import io

import pytest
from PIL import Image

from app.config import settings
from app.models import Piece, PieceImage


@pytest.fixture()
def media_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "MEDIA_DIR", str(tmp_path / "media"))
    return tmp_path / "media"


def jpeg_bytes(size=(600, 750), color=(120, 40, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def upload(client, headers, files=None, fields=None):
    data = {
        "pseudonym": "atelier nord",
        "title": "Veste de minuit",
        "year": "2024",
        "price_cents": "390000",
        "textile": "Wool twill",
        "dims": "M",
        "story": "Cut from a single bolt.",
        "care": "Dry clean only.",
    }
    data.update(fields or {})
    file_list = files if files is not None else [("images", ("coat.jpg", jpeg_bytes(), "image/jpeg"))]
    return client.post("/api/pieces", data=data, files=file_list, headers=headers)


def test_upload_hangs_plate_at_once(client, auth_headers, db, media_dir):
    res = upload(client, auth_headers)
    assert res.status_code == 201, res.text
    piece = db.get(Piece, res.json()["id"])
    assert piece.status == "draft"
    assert len(piece.images) == 1
    img = piece.images[0]
    assert img.slot == 0
    assert img.bg_state == "done"
    assert len(img.dominant_palette) == 3
    assert (media_dir / img.original_path).exists()
    assert (media_dir / img.plate_path).exists()
    assert Image.open(media_dir / img.plate_path).size == (1200, 1500)


def test_wide_upload_cover_crops(client, auth_headers, db, media_dir):
    res = upload(
        client, auth_headers,
        files=[("images", ("wide.jpg", jpeg_bytes(size=(900, 300)), "image/jpeg"))],
    )
    assert res.status_code == 201, res.text
    img = db.get(Piece, res.json()["id"]).images[0]
    assert Image.open(media_dir / img.plate_path).size == (1200, 1500)


def test_published_upload_projects_real_plate(client, auth_headers, db, media_dir):
    res = upload(client, auth_headers)
    pid = res.json()["id"]
    client.post(f"/api/pieces/{pid}/publish", headers=auth_headers)
    res = client.get(f"/api/pieces/{pid}")
    assert res.status_code == 200
    img = res.json()["images"][0]
    assert set(img.keys()) == {"slot", "plate_url", "palette"}
    assert img["plate_url"].startswith("/media/plates/")
    assert len(img["palette"]) == 3


def test_rejects_non_image(client, auth_headers, db, media_dir):
    res = upload(
        client, auth_headers,
        files=[("images", ("note.txt", b"this is not a photograph", "text/plain"))],
    )
    assert res.status_code == 400


def test_rejects_float_price_and_fifth_view(client, auth_headers, db, media_dir):
    res = upload(client, auth_headers, fields={"price_cents": "39.99"})
    assert res.status_code == 400
    files = [("images", (f"v{i}.jpg", jpeg_bytes(), "image/jpeg")) for i in range(5)]
    res = upload(client, auth_headers, files=files)
    assert res.status_code == 400


def test_studio_list_open(client, auth_headers, db, media_dir):
    assert client.get("/api/studio/pieces").status_code == 200
    upload(client, auth_headers)
    res = client.get("/api/studio/pieces", headers=auth_headers)
    assert res.status_code == 200
    piece = res.json()[-1]
    assert piece["status"] == "draft"
    assert piece["images"][0]["bg_state"] == "done"
    assert piece["images"][0]["plate_url"].startswith("/media/plates/")
