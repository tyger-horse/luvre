"""The studio keeps two keys — owner and Raph. No third account, ever."""

from contextlib import nullcontext

import pytest

from app.auth import verify_password
from app.cli import MAX_FOUNDERS, change_password, create_founder
from app.models import User


def _factory(db):
    return lambda: nullcontext(db)


def test_two_founders_then_locked(db):
    assert MAX_FOUNDERS == 2
    first = create_founder(
        "owner@example.ca", "first-studio-password-long",
        "Owner", session_factory=_factory(db),
    )
    assert first.role == "founder"
    assert verify_password("first-studio-password-long", first.password_hash)
    assert "first-studio-password" not in first.password_hash

    create_founder(
        "raph@example.ca", "second-studio-password-long",
        "Raph", session_factory=_factory(db),
    )
    with pytest.raises(SystemExit):
        create_founder(
            "intruder@example.ca", "third-studio-password-long",
            session_factory=_factory(db),
        )
    assert db.query(User).filter(User.role == "founder").count() == 2


def test_email_case_and_space_forgiven_but_password_is_exact(db):
    create_founder(
        "Owner@Example.CA", "exact-password-long-enough",
        session_factory=_factory(db),
    )
    assert db.query(User).filter_by(email="owner@example.ca").count() == 1
    change_password("  OWNER@example.ca ", "rotated-password-long-enough",
                    session_factory=_factory(db))
    from app.auth import verify_password as vp

    user = db.query(User).filter_by(email="owner@example.ca").one()
    assert vp("rotated-password-long-enough", user.password_hash)
    assert not vp("exact-password-long-enough", user.password_hash)
