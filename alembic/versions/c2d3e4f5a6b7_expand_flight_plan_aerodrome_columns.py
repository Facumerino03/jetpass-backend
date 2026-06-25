"""expand flight plan aerodrome columns for local identifiers

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-06-24 16:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "flight_plans",
        "departure_aerodrome_icao",
        existing_type=sa.String(length=4),
        type_=sa.String(length=16),
        existing_nullable=False,
    )
    op.alter_column(
        "flight_plans",
        "destination_aerodrome_icao",
        existing_type=sa.String(length=4),
        type_=sa.String(length=16),
        existing_nullable=False,
    )
    op.alter_column(
        "flight_plans",
        "alternate1_aerodrome_icao",
        existing_type=sa.String(length=4),
        type_=sa.String(length=16),
        existing_nullable=False,
    )
    op.alter_column(
        "flight_plans",
        "alternate2_aerodrome_icao",
        existing_type=sa.String(length=4),
        type_=sa.String(length=16),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "flight_plans",
        "alternate2_aerodrome_icao",
        existing_type=sa.String(length=16),
        type_=sa.String(length=4),
        existing_nullable=False,
    )
    op.alter_column(
        "flight_plans",
        "alternate1_aerodrome_icao",
        existing_type=sa.String(length=16),
        type_=sa.String(length=4),
        existing_nullable=False,
    )
    op.alter_column(
        "flight_plans",
        "destination_aerodrome_icao",
        existing_type=sa.String(length=16),
        type_=sa.String(length=4),
        existing_nullable=False,
    )
    op.alter_column(
        "flight_plans",
        "departure_aerodrome_icao",
        existing_type=sa.String(length=16),
        type_=sa.String(length=4),
        existing_nullable=False,
    )
