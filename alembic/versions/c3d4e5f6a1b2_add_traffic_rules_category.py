"""add traffic type flight rules category to controlled aerodromes

Revision ID: c3d4e5f6a1b2
Revises: b2c3d4e5f6a1
Create Date: 2026-06-07 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a1b2"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("controlled_aerodromes", sa.Column("traffic_type", sa.String(length=20), nullable=True))
    op.add_column("controlled_aerodromes", sa.Column("flight_rules", sa.String(length=20), nullable=True))
    op.add_column("controlled_aerodromes", sa.Column("category", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("controlled_aerodromes", "category")
    op.drop_column("controlled_aerodromes", "flight_rules")
    op.drop_column("controlled_aerodromes", "traffic_type")
