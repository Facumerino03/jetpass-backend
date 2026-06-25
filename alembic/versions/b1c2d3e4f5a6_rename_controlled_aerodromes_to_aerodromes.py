"""rename controlled_aerodromes to aerodromes

Revision ID: b1c2d3e4f5a6
Revises: a9b8c7d6e5f4
Create Date: 2026-06-24 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a9b8c7d6e5f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("controlled_aerodromes", "aerodromes")
    op.execute("ALTER INDEX IF EXISTS ix_controlled_aerodromes_icao_code RENAME TO ix_aerodromes_icao_code")
    op.execute("ALTER INDEX IF EXISTS ix_controlled_aerodromes_is_active RENAME TO ix_aerodromes_is_active")
    op.execute("ALTER INDEX IF EXISTS ix_controlled_aerodromes_local_identifier RENAME TO ix_aerodromes_local_identifier")
    op.execute("ALTER INDEX IF EXISTS ix_controlled_aerodromes_is_controlled RENAME TO ix_aerodromes_is_controlled")


def downgrade() -> None:
    op.execute("ALTER INDEX IF EXISTS ix_aerodromes_is_controlled RENAME TO ix_controlled_aerodromes_is_controlled")
    op.execute("ALTER INDEX IF EXISTS ix_aerodromes_local_identifier RENAME TO ix_controlled_aerodromes_local_identifier")
    op.execute("ALTER INDEX IF EXISTS ix_aerodromes_is_active RENAME TO ix_controlled_aerodromes_is_active")
    op.execute("ALTER INDEX IF EXISTS ix_aerodromes_icao_code RENAME TO ix_controlled_aerodromes_icao_code")
    op.rename_table("aerodromes", "controlled_aerodromes")
