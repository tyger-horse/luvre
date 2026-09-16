"""The studio keeps two keys — owner and Raph. No third account, ever."""

from contextlib import nullcontext

import pytest

from app.auth import verify_password
from app.cli import MAX_FOUNDERS, create_founder
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
