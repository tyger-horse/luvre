"""buyer's chosen coin on crypto commissions

Revision ID: 4f8a2c1d9e3b
Revises: 9c2f1a4b7d3e
Create Date: 2026-09-16

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "4f8a2c1d9e3b"
down_revision = "9c2f1a4b7d3e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("pay_currency", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "pay_currency")
