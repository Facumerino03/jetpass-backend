"""add official_pdf_key to flight_plans

Revision ID: d4e5f6a7b8c9
Revises: 05bbc20fb20c
Create Date: 2026-06-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "05bbc20fb20c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("flight_plans", sa.Column("official_pdf_key", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("flight_plans", "official_pdf_key")
