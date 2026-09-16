from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy import JSON as GenericJSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="founder")
    display_name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Piece(Base):
    __tablename__ = "pieces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # PRIVATE — never serialized publicly. Only `pseudonym` is exposed.
    seller_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    pseudonym: Mapped[str] = mapped_column(String(120), default="atelier anonyme")
    title: Mapped[str] = mapped_column(String(200), default="Untitled")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    micro: Mapped[str] = mapped_column(String(280), default="")
    textile: Mapped[str] = mapped_column(String(200), default="")
    dims: Mapped[str] = mapped_column(String(120), default="")
    story: Mapped[str] = mapped_column(Text, default="")
    care: Mapped[str] = mapped_column(Text, default="")
    # Integer cents (CAD) everywhere. No floats in the money path.
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    images: Mapped[list["PieceImage"]] = relationship(
        "PieceImage", back_populates="piece", cascade="all, delete-orphan"
    )


class PieceImage(Base):
    __tablename__ = "piece_images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    piece_id: Mapped[int] = mapped_column(ForeignKey("pieces.id"), index=True)
    slot: Mapped[int] = mapped_column(Integer, default=0)
    original_path: Mapped[str] = mapped_column(String(512), default="")
    cutout_path: Mapped[str] = mapped_column(String(512), default="")
    plate_path: Mapped[str] = mapped_column(String(512), default="")
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    dominant_palette: Mapped[list | None] = mapped_column(GenericJSON, nullable=True)
    bg_state: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    piece: Mapped[Piece] = relationship("Piece", back_populates="images")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    piece_id: Mapped[int] = mapped_column(ForeignKey("pieces.id"), index=True)
    buyer_name: Mapped[str] = mapped_column(String(200), default="")
    buyer_email: Mapped[str] = mapped_column(String(320), default="")
    buyer_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="created")
    method: Mapped[str] = mapped_column(String(32), default="interac")
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="CAD")
    reference_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    provider_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    handover_area: Mapped[str | None] = mapped_column(String(120), nullable=True)
    handover_window: Mapped[str | None] = mapped_column(String(200), nullable=True)
    handover_place_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    piece: Mapped[Piece] = relationship("Piece")


class PaymentEvent(Base):
    __tablename__ = "payment_events"
    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_provider_event"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    provider_event_id: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(128), default="")
    signature_valid: Mapped[bool] = mapped_column(default=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
