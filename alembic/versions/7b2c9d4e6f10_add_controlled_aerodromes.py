"""add controlled aerodromes

Revision ID: 7b2c9d4e6f10
Revises: 1f415d96c495
Create Date: 2026-05-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7b2c9d4e6f10"
down_revision: Union[str, Sequence[str], None] = "1f415d96c495"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "controlled_aerodromes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("icao_code", sa.String(length=4), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_controlled_aerodromes_icao_code"), "controlled_aerodromes", ["icao_code"], unique=True)
    op.create_index(op.f("ix_controlled_aerodromes_is_active"), "controlled_aerodromes", ["is_active"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_controlled_aerodromes_is_active"), table_name="controlled_aerodromes")
    op.drop_index(op.f("ix_controlled_aerodromes_icao_code"), table_name="controlled_aerodromes")
    op.drop_table("controlled_aerodromes")
