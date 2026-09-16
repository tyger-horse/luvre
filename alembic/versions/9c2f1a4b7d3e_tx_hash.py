"""manual crypto proof: tx_hash on orders

Revision ID: 9c2f1a4b7d3e
Revises: 75e1a8df16c6
Create Date: 2026-09-16

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "9c2f1a4b7d3e"
down_revision = "75e1a8df16c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("tx_hash", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "tx_hash")
