from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db import SessionLocal, get_db, init_db
from app.models import Order, PaymentEvent, Piece, PieceImage
from app.payments import paypal as paypal_provider
from app.payments.crypto import (
    COINS,
    deposit_address,
    is_confirmed,
    verify_btpay_signature,
    verify_coinbase_signature,
)
from app.payments.interac import transfer_instructions
from app.payments.paypal import PayPalError, PayPalNotConfigured
from app.schemas import (
    OrderCreate,
    OrderStatusOut,
    PieceCreate,
    PiecePatch,
    PublicPiece,
    PublicPieceImage,
    ScheduleIn,
    StudioOrderOut,
    StudioPiece,
    StudioPieceImage,
)
from app.services.background import (
    MAX_SLOTS,
    decode_upload,
    store_upload,
)
from app.services.orders import (
    IllegalTransition,
    generate_reference_code,
    transition,
    ttl_hours,
)
from app.workers import start_workers

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    Path(settings.MEDIA_DIR).mkdir(parents=True, exist_ok=True)
    ensure_seed_data()
    start_workers()
    yield


app = FastAPI(title="£UVR€", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.PUBLIC_BASE_URL],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)


# --- Public projection (§2.1): exactly the §10 key set, nothing else. ---


def project_image(img: PieceImage) -> PublicPieceImage:
    plate_url = f"/media/{img.plate_path}" if img.plate_path else ""
    palette = img.dominant_palette or ["#2a2a2a", "#3a3a3a", "#4a4a4a"]
    return PublicPieceImage(slot=img.slot, plate_url=plate_url, palette=palette[:3])


def project_piece(piece: Piece) -> PublicPiece:
    if not isinstance(piece.price_cents, int) or isinstance(piece.price_cents, bool):
        raise ValueError("price_cents must be integer cents")
    if piece.status not in ("published", "sold"):
        raise ValueError("only the wall hangs publicly")
    return PublicPiece(
        id=piece.id,
        pseudonym=piece.pseudonym,
        title=piece.title,
        year=piece.year,
        micro=piece.micro,
        textile=piece.textile,
        dims=piece.dims,
        price_cents=piece.price_cents,
        story=piece.story,
        care=piece.care,
        images=[project_image(i) for i in sorted(piece.images, key=lambda x: x.slot)],
        status=piece.status,
    )


def ensure_seed_data() -> None:
    with SessionLocal() as db:
        if db.scalar(select(Piece).limit(1)) is not None:
            return
        seeds = [
            Piece(
                pseudonym="atelier nord",
                title="Veste de minuit",
                year=2024,
                micro="Wool overcoat, cut like a doorway.",
                textile="Wool twill",
                dims="M · chest 102 cm",
                story="Cut in Mile End from a single bolt of midnight wool.",
                care="Dry clean only. Air between wearings.",
                price_cents=390000,
                status="published",
                published_at=datetime.now(timezone.utc),
            ),
            Piece(
                pseudonym="main blanche",
                title="Robe d'aube",
                year=2023,
                micro="Silk dress the colour of first light.",
                textile="Raw silk",
                dims="S · length 118 cm",
                story="One seam, one morning, one wearer.",
                care="Hand wash cold. Dry flat in shade.",
                price_cents=145000,
                status="published",
                published_at=datetime.now(timezone.utc),
            ),
        ]
        for piece in seeds:
            db.add(piece)
            db.flush()
            db.add(
                PieceImage(
                    piece_id=piece.id,
                    slot=0,
                    dominant_palette=["#1d3b2a", "#cac4ce", "#0e1f16"],
                    bg_state="pending",
                )
            )
        db.commit()


# --- Studio auth: retired. No accounts — the hidden knock is the only
# door, and the money roads already pay Raph directly. ---


@app.get("/api/health", include_in_schema=False)
def health():
    return {"ok": True}


# --- Public gallery feed (projected; prices travel but render only in the dossier) ---


@app.get("/api/pieces", response_model=list[PublicPiece])
def list_pieces(db: Session = Depends(get_db)):
    held = held_piece_ids(db)
    pieces = db.scalars(
        select(Piece)
        .options(selectinload(Piece.images))
        .where(Piece.status.in_(["published", "sold"]))
        .order_by(Piece.published_at.desc().nullslast(), Piece.id.desc())
    ).all()
    return [project_piece(p) for p in pieces if p.id not in held]


@app.get("/api/pieces/{piece_id}", response_model=PublicPiece)
def get_piece(piece_id: int, db: Session = Depends(get_db)):
    piece = db.scalar(
        select(Piece)
        .options(selectinload(Piece.images))
        .where(Piece.id == piece_id, Piece.status.in_(["published", "sold"]))
    )
    if piece is None or piece.id in held_piece_ids(db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This piece is not on the wall.")
    return project_piece(piece)


# --- Studio piece desk (M1: JSON fields or multipart with photographs) ---


def _media_url(rel: str) -> str:
    return f"/media/{rel}" if rel else ""


def studio_project(piece: Piece) -> StudioPiece:
    return StudioPiece(
        id=piece.id,
        title=piece.title,
        pseudonym=piece.pseudonym,
        year=piece.year,
        micro=piece.micro,
        textile=piece.textile,
        dims=piece.dims,
        story=piece.story,
        care=piece.care,
        price_cents=piece.price_cents,
        status=piece.status,
        images=[
            StudioPieceImage(
                id=img.id,
                slot=img.slot,
                bg_state=img.bg_state,
                plate_url=_media_url(img.plate_path),
                original_url=_media_url(img.original_path),
                cutout_url=_media_url(img.cutout_path),
                palette=img.dominant_palette or [],
                width=img.width,
                height=img.height,
            )
            for img in sorted(piece.images, key=lambda x: x.slot)
        ],
    )


def _parse_int_field(value: str | None, name: str, required: bool = False) -> int | None:
    if value is None or value == "":
        if required:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{name} must be whole cents.")
        return None
    if not value.strip().isdigit():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{name} must be a whole number — no decimals, no floats.",
        )
    return int(value.strip())


@app.post("/api/pieces", status_code=status.HTTP_201_CREATED)
async def create_piece(
    request: Request,
    db: Session = Depends(get_db),
):
    ctype = request.headers.get("content-type", "")
    if "multipart/form-data" in ctype:
        form = await request.form()
        fields = {k: form.get(k) for k in (
            "title", "pseudonym", "year", "micro", "textile", "dims", "story", "care")}
        price_cents = _parse_int_field(str(form.get("price_cents") or ""), "price_cents")
        year = _parse_int_field(str(form.get("year") or ""), "year")
        body = PieceCreate(
            title=(fields["title"] or "Untitled").strip() or "Untitled",
            pseudonym=(fields["pseudonym"] or "atelier anonyme").strip() or "atelier anonyme",
            year=year,
            micro=(fields["micro"] or "").strip(),
            textile=(fields["textile"] or "").strip(),
            dims=(fields["dims"] or "").strip(),
            story=(fields["story"] or "").strip(),
            care=(fields["care"] or "").strip(),
            price_cents=price_cents if price_cents is not None else 0,
        )
        uploads = form.getlist("images")
        if len(uploads) > MAX_SLOTS:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Four views at most — the hanging plus three details.",
            )
        datas = []
        for upload in uploads:
            data = await upload.read()
            try:
                decode_upload(data)  # validate before anything is persisted
            except ValueError as exc:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
            datas.append(data)
    else:
        try:
            payload = await request.json()
        except Exception:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unrepeatable draft.")
        body = PieceCreate(**payload)
        datas = []

    piece = Piece(seller_user_id=None, status="draft", **body.model_dump())
    db.add(piece)
    db.flush()
    for slot, data in enumerate(datas):
        stored = store_upload(data)
        image = PieceImage(
            piece_id=piece.id,
            slot=slot,
            original_path=stored["original_path"],
            plate_path=stored["plate_path"],
            width=stored["width"],
            height=stored["height"],
            dominant_palette=stored["palette"],
            bg_state="done",
        )
        db.add(image)
    db.commit()
    db.refresh(piece)
    return {"id": piece.id, "status": piece.status}


@app.get("/api/studio/pieces", response_model=list[StudioPiece])
def studio_pieces(db: Session = Depends(get_db)):
    pieces = db.scalars(
        select(Piece).options(selectinload(Piece.images)).order_by(Piece.id.desc())
    ).all()
    return [studio_project(p) for p in pieces]


# --- Commissions (M2: Interac e-Transfer + pay at handover) ---

HELD_STATUSES = ("created", "awaiting_payment", "reserved")


def held_piece_ids(db: Session) -> set[int]:
    return set(
        db.scalars(select(Order.piece_id).where(Order.status.in_(HELD_STATUSES))).all()
    )


def order_instructions(order: Order, db: Session) -> str | None:
    if order.method == "interac" and order.status == "awaiting_payment":
        return transfer_instructions(
            order.amount_cents,
            order.reference_code,
            settings.INTERAC_TRANSFER_EMAIL,
            ttl_hours(),
        )
    if order.method == "on_delivery" and order.status == "reserved":
        return (
            f"The piece is held for you for {ttl_hours()} hours. "
            f"Bring nothing but yourself to {order.handover_area or 'Montreal'} — "
            "the desk confirms the hour."
        )
    if order.method == "crypto" and order.status == "awaiting_payment":
        dollars = order.amount_cents / 100
        if order.tx_hash:
            return (
                "The desk has your proof and is watching the chain. "
                "Only the confirmed settlement marks the piece yours."
            )
        coin = (order.pay_currency or "eth").lower()
        label = COINS.get(coin, COINS["eth"])["label"]
        return (
            f"Send CAD ${dollars:,.2f} worth of {label} to {deposit_address(coin)}, "
            f"then press “sent” below and paste the transaction hash with {order.reference_code} "
            "kept close. The piece is held for you for "
            f"{ttl_hours()} hours."
        )
    return None


def project_order(order: Order, db: Session) -> OrderStatusOut:
    piece = db.get(Piece, order.piece_id)
    return OrderStatusOut(
        id=order.id,
        reference_code=order.reference_code,
        status=order.status,
        method=order.method,
        amount_cents=order.amount_cents,
        currency=order.currency,
        expires_at=order.expires_at,
        paid_at=order.paid_at,
        handover_area=order.handover_area,
        handover_window=order.handover_window,
        handover_place_note=order.handover_place_note,
        piece_title=piece.title if piece else "",
        piece_pseudonym=piece.pseudonym if piece else "",
        instructions=order_instructions(order, db),
        tx_hash=order.tx_hash,
        pay_currency=order.pay_currency,
    )


@app.post("/api/orders", status_code=status.HTTP_201_CREATED)
def create_order(body: OrderCreate, db: Session = Depends(get_db)):
    if body.method not in ("interac", "on_delivery", "paypal", "crypto"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "That road is still being paved — ask the desk what is open.",
        )
    if not body.buyer_name.strip() or "@" not in body.buyer_email:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "A name and a reachable contact, so the desk can find you.",
        )
    if body.method == "on_delivery" and not (body.handover_area or "").strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Choose the quarter where you would like to meet.",
        )
    if body.method == "crypto":
        coin = (body.pay_currency or "").strip().lower()
        if coin not in COINS:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Choose a coin — Ethereum, Bitcoin, or USD Coin.",
            )
    else:
        coin = None
    piece = db.get(Piece, body.piece_id)
    if piece is None or piece.status != "published":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This piece is not on the wall.")
    held = db.scalar(
        select(Order.id).where(
            Order.piece_id == piece.id, Order.status.in_(HELD_STATUSES)
        )
    )
    if held is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Another commission already holds this piece.",
        )
    reference = generate_reference_code()
    while db.scalar(select(Order.id).where(Order.reference_code == reference)):
        reference = generate_reference_code()
    now = datetime.now(timezone.utc)
    order = Order(
        piece_id=piece.id,
        buyer_name=body.buyer_name.strip(),
        buyer_email=body.buyer_email.strip(),
        buyer_phone=(body.buyer_phone or "").strip() or None,
        status="created",
        method=body.method,
        amount_cents=piece.price_cents,
        currency="CAD",
        reference_code=reference,
        handover_area=(body.handover_area or "").strip() or None,
        handover_window=(body.handover_window or "").strip() or None,
        pay_currency=coin,
        created_at=now,
        expires_at=now + timedelta(hours=ttl_hours()),
    )
    db.add(order)
    db.flush()
    if body.method == "paypal":
        base = settings.PUBLIC_BASE_URL.rstrip("/")
        try:
            created = paypal_provider.create_order(
                amount_cents=piece.price_cents,
                reference_code=reference,
                return_url=f"{base}/?commission={order.id}",
                cancel_url=f"{base}/?commission={order.id}&cancelled=1",
            )
        except PayPalNotConfigured as exc:
            db.rollback()
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
        except PayPalError as exc:
            db.rollback()
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
        order.provider_ref = created["provider_ref"]
        approval_url: str | None = created["approval_url"]
        checkout_url: str | None = None
    elif body.method == "crypto":
        # Manual wallet: the buyer sends to the deposit address, then
        # pastes the transaction hash as proof. The desk verifies
        # on-chain and marks paid — no provider, no hosted checkout.
        approval_url = None
        checkout_url = None
    else:
        approval_url = None
        checkout_url = None
    transition(order, "provider_ready" if body.method in ("interac", "paypal", "crypto") else "reserve_on_delivery")
    db.commit()
    db.refresh(order)
    out = project_order(order, db)
    out.approval_url = approval_url
    out.checkout_url = checkout_url
    return out


@app.get("/api/orders/{order_id}", response_model=OrderStatusOut)
def order_status(order_id: int, code: str = "", db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if order is None or not code or order.reference_code != code.strip().upper():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This commission cannot be found.")
    return project_order(order, db)


class TxHashIn(BaseModel):
    code: str = ""
    tx_hash: str = ""


@app.post("/api/orders/{order_id}/tx-hash", response_model=OrderStatusOut)
def submit_tx_hash(order_id: int, body: TxHashIn, db: Session = Depends(get_db)):
    """“I've sent the money” — the buyer pastes the transaction hash as proof."""
    import re

    order = db.get(Order, order_id)
    if order is None or not body.code or order.reference_code != body.code.strip().upper():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This commission cannot be found.")
    if order.method != "crypto" or order.status != "awaiting_payment":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This commission needs no proof.")
    cleaned = body.tx_hash.strip()
    if not re.fullmatch(r"[0-9a-zA-Z]{8,128}", cleaned):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "That does not read as a transaction hash — paste the whole of it.",
        )
    order.tx_hash = cleaned
    db.commit()
    db.refresh(order)
    return project_order(order, db)


@app.post("/api/orders/{order_id}/paypal/return")
def paypal_return(order_id: int, db: Session = Depends(get_db)):
    """Convenience after the PayPal redirect: attempt capture, report standing.

    Never marks paid — only the verified webhook does that.
    """
    order = db.get(Order, order_id)
    if order is None or order.method != "paypal" or not order.provider_ref:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This commission cannot be found.")
    try:
        result = paypal_provider.capture_order(order.provider_ref)
    except (PayPalError, PayPalNotConfigured):
        result = {"captured": False, "status": "unknown"}
    return {
        "order_id": order.id,
        "order_status": order.status,
        "captured": result["captured"],
    }


@app.post("/webhooks/paypal")
async def paypal_webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    headers = dict(request.headers)
    if not paypal_provider.verify_webhook_signature(headers, raw):
        return JSONResponse(status_code=400, content={"detail": "Invalid webhook signature."})
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JSONResponse(status_code=400, content={"detail": "Unreadable webhook body."})
    event_id = str(payload.get("id") or "")
    event_type = str(payload.get("event_type") or "")
    if not event_id:
        return JSONResponse(status_code=400, content={"detail": "Webhook missing id."})
    reference, related_order = paypal_provider.order_id_from_event(payload)
    order = None
    if reference:
        order = db.scalar(select(Order).where(Order.reference_code == reference))
    if order is None and related_order:
        order = db.scalar(select(Order).where(Order.provider_ref == related_order))
    if order is None:
        return JSONResponse(status_code=404, content={"detail": "No such commission."})
    existing = db.scalar(
        select(PaymentEvent).where(
            PaymentEvent.provider == "paypal",
            PaymentEvent.provider_event_id == event_id,
        )
    )
    if existing is not None:
        return {"status": "duplicate", "order_status": order.status}
    db.add(
        PaymentEvent(
            order_id=order.id,
            provider="paypal",
            provider_event_id=event_id,
            event_type=event_type,
            signature_valid=True,
        )
    )
    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        try:
            transition(order, "payment_confirmed", db.get(Piece, order.piece_id))
        except IllegalTransition:
            pass
    db.commit()
    return {"status": "recorded", "order_status": order.status}


def _desk_project(order: Order, db: Session) -> StudioOrderOut:
    piece = db.get(Piece, order.piece_id)
    return StudioOrderOut(
        id=order.id,
        piece_id=order.piece_id,
        piece_title=piece.title if piece else "",
        buyer_name=order.buyer_name,
        buyer_email=order.buyer_email,
        buyer_phone=order.buyer_phone,
        status=order.status,
        method=order.method,
        amount_cents=order.amount_cents,
        reference_code=order.reference_code,
        tx_hash=order.tx_hash,
        pay_currency=order.pay_currency,
        handover_area=order.handover_area,
        handover_window=order.handover_window,
        handover_place_note=order.handover_place_note,
        expires_at=order.expires_at,
        paid_at=order.paid_at,
        created_at=order.created_at,
    )


@app.get("/api/studio/orders", response_model=list[StudioOrderOut])
def studio_orders(db: Session = Depends(get_db)):
    orders = db.scalars(select(Order).order_by(Order.id.desc())).all()
    return [_desk_project(o, db) for o in orders]


@app.post("/api/studio/orders/{order_id}/mark-paid", response_model=StudioOrderOut)
def studio_mark_paid(
    order_id: int, db: Session = Depends(get_db)
):
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such commission.")
    try:
        transition(order, "payment_confirmed", db.get(Piece, order.piece_id))
    except IllegalTransition:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This commission cannot be marked paid.")
    db.commit()
    db.refresh(order)
    return _desk_project(order, db)


@app.post("/api/studio/orders/{order_id}/schedule", response_model=StudioOrderOut)
def studio_schedule(
    order_id: int,
    body: ScheduleIn,
    db: Session = Depends(get_db),
):
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such commission.")
    if body.handover_window is not None:
        order.handover_window = body.handover_window
    if body.handover_place_note is not None:
        order.handover_place_note = body.handover_place_note
    try:
        transition(order, "handover_scheduled")
    except IllegalTransition:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Settle the commission before naming the hour.")
    db.commit()
    db.refresh(order)
    return _desk_project(order, db)


@app.post("/api/studio/orders/{order_id}/complete", response_model=StudioOrderOut)
def studio_complete(
    order_id: int, db: Session = Depends(get_db)
):
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such commission.")
    try:
        transition(order, "handover_done")
    except IllegalTransition:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only a scheduled handover can be completed.")
    db.commit()
    db.refresh(order)
    return _desk_project(order, db)


@app.post("/api/studio/orders/{order_id}/cancel", response_model=StudioOrderOut)
def studio_cancel(
    order_id: int, db: Session = Depends(get_db)
):
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such commission.")
    try:
        transition(order, "cancelled")
    except IllegalTransition:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This commission is past cancelling.")
    db.commit()
    db.refresh(order)
    return _desk_project(order, db)


@app.patch("/api/pieces/{piece_id}")
def patch_piece(piece_id: int, body: PiecePatch, db: Session = Depends(get_db)):
    piece = db.get(Piece, piece_id)
    if piece is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such piece.")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(piece, field, value)
    db.commit()
    return {"id": piece.id, "status": piece.status}


def _set_piece_status(piece_id: int, to: str, db: Session) -> dict:
    piece = db.get(Piece, piece_id)
    if piece is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such piece.")
    if to == "published":
        piece.status = "published"
        piece.published_at = datetime.now(timezone.utc)
    elif to in ("retired", "sold"):
        piece.status = "sold" if to == "sold" else "retired"
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown atelier action.")
    db.commit()
    return {"id": piece.id, "status": piece.status}


@app.post("/api/pieces/{piece_id}/publish")
def publish_piece(piece_id: int, db: Session = Depends(get_db)):
    return _set_piece_status(piece_id, "published", db)


@app.post("/api/pieces/{piece_id}/retire")
def retire_piece(piece_id: int, db: Session = Depends(get_db)):
    return _set_piece_status(piece_id, "retired", db)


@app.post("/api/pieces/{piece_id}/mark-sold")
def mark_sold_piece(piece_id: int, db: Session = Depends(get_db)):
    return _set_piece_status(piece_id, "sold", db)


# --- Crypto webhook (M4 handler skeleton; signature + idempotency live now) ---


@app.post("/webhooks/crypto")
async def crypto_webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    if "btcpay-sig" in headers:
        secret = settings.BTPAY_WEBHOOK_SECRET or "test-secret"
        valid = verify_btpay_signature(raw, headers["btcpay-sig"], secret)
    else:
        secret = settings.COINBASE_WEBHOOK_SECRET or "test-secret"
        signature = headers.get("x-cc-webhook-signature", "")
        timestamp = headers.get("x-cc-webhook-timestamp", "")
        valid = bool(signature) and verify_coinbase_signature(raw, timestamp, signature, secret)
    if not valid:
        return JSONResponse(status_code=400, content={"detail": "Invalid webhook signature."})
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JSONResponse(status_code=400, content={"detail": "Unreadable webhook body."})
    data = payload.get("data", {}) or {}
    meta = data.get("metadata", {}) or payload.get("metadata", {}) or {}
    event_id = str(
        payload.get("id") or payload.get("event_id") or data.get("id")
        or payload.get("invoiceId") or ""
    )
    event_type = str(payload.get("type") or payload.get("event_type") or "")
    if not event_id:
        return JSONResponse(status_code=400, content={"detail": "Webhook missing id."})
    order = None
    reference = meta.get("reference")
    if reference:
        order = db.scalar(select(Order).where(Order.reference_code == str(reference)))
    if order is None:
        order_pk = meta.get("order_id") or meta.get("orderId") or payload.get("order_id")
        if order_pk is not None:
            try:
                order = db.get(Order, int(order_pk))
            except (ValueError, TypeError):
                order = None
    if order is None:
        charge_ref = data.get("id") or payload.get("invoiceId")
        if charge_ref:
            order = db.scalar(select(Order).where(Order.provider_ref == str(charge_ref)))
    if order is None:
        return JSONResponse(status_code=404, content={"detail": "No such commission."})
    # The idempotency key spans id + type: one invoice speaks several
    # times (received, settled), and each word must be heard once.
    delivery_id = f"{event_id}|{event_type}"
    existing = db.scalar(
        select(PaymentEvent).where(
            PaymentEvent.provider == "crypto",
            PaymentEvent.provider_event_id == delivery_id,
        )
    )
    if existing is not None:
        return {"status": "duplicate", "order_status": order.status}
    db.add(
        PaymentEvent(
            order_id=order.id,
            provider="crypto",
            provider_event_id=delivery_id,
            event_type=event_type,
            signature_valid=True,
        )
    )
    if is_confirmed(event_type):
        try:
            transition(order, "payment_confirmed", order.piece)
        except IllegalTransition:
            pass
    db.commit()
    return {"status": "recorded", "order_status": order.status}


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    media_dir = Path(settings.MEDIA_DIR)
    media_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=media_dir), name="media")

    @app.get("/", include_in_schema=False)
    def gallery():
        from fastapi.responses import FileResponse

        return FileResponse(STATIC_DIR / "index.html")
