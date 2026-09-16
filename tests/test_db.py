"""Database URL normalization — both Heroku-style spellings land on psycopg."""

import pytest
from sqlalchemy.engine import make_url

from app.db import normalize_database_url


@pytest.mark.parametrize(
    "given",
    [
        "postgres://u:p@host:5432/db",
        "postgresql://u:p@host:5432/db",
    ],
)
def test_both_postgres_spellings_use_psycopg(given):
    url = make_url(normalize_database_url(given))
    assert url.drivername == "postgresql+psycopg"


def test_sqlite_and_other_urls_untouched():
    assert normalize_database_url("sqlite:///./luvre.db") == "sqlite:///./luvre.db"
    assert (
        normalize_database_url("postgresql+psycopg://u:p@host/db")
        == "postgresql+psycopg://u:p@host/db"
    )
