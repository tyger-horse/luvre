from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, StrictInt


# --- Public projection (§10). Exact key set — adding keys here is a leak. ---
PUBLIC_PIECE_KEYS = frozenset(
    {
        "id",
        "pseudonym",
        "title",
        "year",
        "micro",
        "textile",
        "dims",
        "price_cents",
        "story",
        "care",
        "images",
        "status",  # "published" | "sold" only — the wall never serves drafts
    }
)
PUBLIC_IMAGE_KEYS = frozenset({"slot", "plate_url", "palette"})


class PublicPieceImage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot: int
    plate_url: str
    palette: list[str]


class PublicPiece(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    pseudonym: str
    title: str
    year: int | None = None
    micro: str = ""
    textile: str = ""
    dims: str = ""
    price_cents: StrictInt
    story: str = ""
    care: str = ""
    images: list[PublicPieceImage] = []
    status: str = "published"


# --- Studio schemas (full fields, never served publicly) ---


class PieceCreate(BaseModel):
    title: str = "Untitled"
    pseudonym: str = "atelier anonyme"
    year: int | None = None
    micro: str = ""
    textile: str = ""
    dims: str = ""
    story: str = ""
    care: str = ""
    price_cents: StrictInt = 0


class PiecePatch(BaseModel):
    title: str | None = None
    pseudonym: str | None = None
    year: int | None = None
    micro: str | None = None
    textile: str | None = None
    dims: str | None = None
    story: str | None = None
    care: str | None = None
    price_cents: StrictInt | None = None


class StudioPieceImage(BaseModel):
    id: int
    slot: int
    bg_state: str
    plate_url: str
    original_url: str
    cutout_url: str
    palette: list[str] = []
    width: int = 0
    height: int = 0


class StudioPiece(BaseModel):
    id: int
    title: str
    pseudonym: str
    year: int | None = None
    micro: str = ""
    textile: str = ""
    dims: str = ""
    story: str = ""
    care: str = ""
    price_cents: StrictInt
    status: str
    images: list[StudioPieceImage] = []


# --- Commissions (M2) ---


class OrderCreate(BaseModel):
    piece_id: int
    method: str
    buyer_name: str = ""
    buyer_email: str = ""
    buyer_phone: str | None = None
    handover_area: str | None = None
    handover_window: str | None = None
    pay_currency: str | None = None  # crypto only: eth | btc | usdc


class OrderStatusOut(BaseModel):
    id: int
    reference_code: str
    status: str
    method: str
    amount_cents: StrictInt
    currency: str = "CAD"
    expires_at: datetime | None = None
    paid_at: datetime | None = None
    handover_area: str | None = None
    handover_window: str | None = None
    handover_place_note: str | None = None
    piece_title: str = ""
    piece_pseudonym: str = ""
    instructions: str | None = None
    approval_url: str | None = None
    checkout_url: str | None = None
    tx_hash: str | None = None
    pay_currency: str | None = None


class ScheduleIn(BaseModel):
    handover_window: str | None = None
    handover_place_note: str | None = None


class StudioOrderOut(BaseModel):
    id: int
    piece_id: int
    piece_title: str = ""
    buyer_name: str = ""
    buyer_email: str = ""
    buyer_phone: str | None = None
    status: str
    method: str
    amount_cents: StrictInt
    reference_code: str
    tx_hash: str | None = None
    pay_currency: str | None = None
    handover_area: str | None = None
    handover_window: str | None = None
    handover_place_note: str | None = None
    expires_at: datetime | None = None
    paid_at: datetime | None = None
    created_at: datetime | None = None
