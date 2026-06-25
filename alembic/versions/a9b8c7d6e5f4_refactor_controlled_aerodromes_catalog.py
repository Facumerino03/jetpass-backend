"""refactor controlled aerodromes catalog

Revision ID: a9b8c7d6e5f4
Revises: 3db4b5b64cdf
Create Date: 2026-06-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a9b8c7d6e5f4"
down_revision: Union[str, None] = "3db4b5b64cdf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("controlled_aerodromes", sa.Column("local_identifier", sa.String(length=16), nullable=True))
    op.add_column("controlled_aerodromes", sa.Column("is_controlled", sa.Boolean(), nullable=True))

    op.execute(
        """
        UPDATE controlled_aerodromes
        SET local_identifier = icao_code,
            is_controlled = TRUE
        WHERE local_identifier IS NULL
        """
    )

    op.alter_column("controlled_aerodromes", "local_identifier", nullable=False)
    op.alter_column("controlled_aerodromes", "is_controlled", nullable=False, server_default=sa.false())

    op.alter_column("controlled_aerodromes", "icao_code", existing_type=sa.String(length=4), nullable=True)
    op.alter_column("controlled_aerodromes", "latitude", existing_type=sa.Float(), nullable=False, server_default="0")
    op.alter_column("controlled_aerodromes", "longitude", existing_type=sa.Float(), nullable=False, server_default="0")

    op.drop_index(op.f("ix_controlled_aerodromes_icao_code"), table_name="controlled_aerodromes")
    op.create_index(op.f("ix_controlled_aerodromes_icao_code"), "controlled_aerodromes", ["icao_code"], unique=False)
    op.create_index(
        op.f("ix_controlled_aerodromes_local_identifier"),
        "controlled_aerodromes",
        ["local_identifier"],
        unique=True,
    )
    op.create_index(
        op.f("ix_controlled_aerodromes_is_controlled"),
        "controlled_aerodromes",
        ["is_controlled"],
        unique=False,
    )

    op.drop_column("controlled_aerodromes", "traffic_type")
    op.drop_column("controlled_aerodromes", "flight_rules")
    op.drop_column("controlled_aerodromes", "category")

    op.alter_column("controlled_aerodromes", "latitude", server_default=None)
    op.alter_column("controlled_aerodromes", "longitude", server_default=None)
    op.alter_column("controlled_aerodromes", "is_controlled", server_default=None)


def downgrade() -> None:
    op.add_column("controlled_aerodromes", sa.Column("category", sa.String(length=20), nullable=True))
    op.add_column("controlled_aerodromes", sa.Column("flight_rules", sa.String(length=20), nullable=True))
    op.add_column("controlled_aerodromes", sa.Column("traffic_type", sa.String(length=20), nullable=True))

    op.drop_index(op.f("ix_controlled_aerodromes_is_controlled"), table_name="controlled_aerodromes")
    op.drop_index(op.f("ix_controlled_aerodromes_local_identifier"), table_name="controlled_aerodromes")
    op.drop_index(op.f("ix_controlled_aerodromes_icao_code"), table_name="controlled_aerodromes")
    op.create_index(op.f("ix_controlled_aerodromes_icao_code"), "controlled_aerodromes", ["icao_code"], unique=True)

    op.alter_column("controlled_aerodromes", "longitude", existing_type=sa.Float(), nullable=True)
    op.alter_column("controlled_aerodromes", "latitude", existing_type=sa.Float(), nullable=True)
    op.alter_column("controlled_aerodromes", "icao_code", existing_type=sa.String(length=4), nullable=False)

    op.drop_column("controlled_aerodromes", "is_controlled")
    op.drop_column("controlled_aerodromes", "local_identifier")
