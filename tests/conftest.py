import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only-long-enough")
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("PUBLIC_BASE_URL", "http://testserver")
os.environ.setdefault("COINBASE_WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("LUVRE_RUN_WORKER", "0")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import pytest

from app.db import get_db
from app.main import app, project_piece
from app.models import Base, Piece, PieceImage

engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    def override():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def published_piece(db):
    piece = Piece(
        seller_user_id=None,
        pseudonym="atelier nord",
        title="Veste de minuit",
        year=2024,
        micro="Wool overcoat, cut like a doorway.",
        textile="Wool twill",
        dims="M",
        story="Cut from a single bolt.",
        care="Dry clean only.",
        price_cents=390000,
        status="published",
    )
    db.add(piece)
    db.flush()
    db.add(
        PieceImage(
            piece_id=piece.id,
            slot=0,
            plate_path="",
            dominant_palette=["#1d3b2a", "#cac4ce", "#0e1f16"],
            bg_state="done",
        )
    )
    db.commit()
    db.refresh(piece)
    return piece


@pytest.fixture()
def auth_headers():
    # No accounts: the knock is the only door. Endpoints ignore auth,
    # so tests pass empty headers straight through.
    return {}
