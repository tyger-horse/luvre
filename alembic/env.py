"""Alembic environment — schema migrations for £UVR€ (M6).

Reads DATABASE_URL from the same settings the app uses, so
`alembic upgrade head` works in the container at boot and on dev machines.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alembic import context
from sqlalchemy import create_engine

from app.config import settings
from app.db import normalize_database_url
from app.models import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=normalize_database_url(settings.DATABASE_URL),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connect_args = (
        {"check_same_thread": False}
        if settings.DATABASE_URL.startswith("sqlite")
        else {}
    )
    engine = create_engine(normalize_database_url(settings.DATABASE_URL), connect_args=connect_args)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
