"""initial

Revision ID: 357a662aee93
Revises: 
Create Date: 2026-05-08 20:39:53.978879

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '357a662aee93'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('first_name', sa.String(100), nullable=False),
        sa.Column('last_name', sa.String(100), nullable=False),
        sa.Column('phone', sa.String(30), nullable=True),
        sa.Column(
            'role',
            sa.Enum('pilot', 'atc_authority', 'airport_operator', 'admin', name='role'),
            nullable=False,
        ),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    op.create_table(
        'aircraft',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('owner_user_id', sa.Uuid(), nullable=False),
        sa.Column('alias', sa.String(120), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('identification', sa.String(20), nullable=False),
        sa.Column('icao_type_designator', sa.String(10), nullable=False),
        sa.Column(
            'wake_turbulence_category',
            sa.Enum('L', 'M', 'H', 'J', name='waketurbulencecat'),
            nullable=False,
        ),
        sa.Column('equipment_com_nav', sa.String(80), nullable=False),
        sa.Column('equipment_surveillance', sa.String(80), nullable=False),
        sa.Column('pbn_capabilities', sa.String(80), nullable=True),
        sa.Column('emergency_radio', sa.String(20), nullable=True),
        sa.Column('survival_equipment', sa.String(20), nullable=True),
        sa.Column('life_jackets', sa.String(20), nullable=True),
        sa.Column('dinghies_number', sa.Integer(), nullable=True),
        sa.Column('dinghies_capacity', sa.Integer(), nullable=True),
        sa.Column('dinghies_cover', sa.Boolean(), nullable=True),
        sa.Column('dinghies_color', sa.String(40), nullable=True),
        sa.Column('color_and_markings', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index(op.f('ix_aircraft_owner_user_id'), 'aircraft', ['owner_user_id'])
    op.create_index(op.f('ix_aircraft_identification'), 'aircraft', ['identification'])

    op.create_table(
        'auth_sessions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('refresh_token_hash', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('device_name', sa.String(120), nullable=True),
        sa.Column('user_agent', sa.String(255), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index(op.f('ix_auth_sessions_user_id'), 'auth_sessions', ['user_id'])
    op.create_index(op.f('ix_auth_sessions_refresh_token_hash'), 'auth_sessions', ['refresh_token_hash'], unique=True)


def downgrade() -> None:
    op.drop_table('auth_sessions')
    op.drop_table('aircraft')
    op.drop_table('users')

    op.execute(sa.text('DROP TYPE IF EXISTS waketurbulencecat'))
    op.execute(sa.text('DROP TYPE IF EXISTS role'))
