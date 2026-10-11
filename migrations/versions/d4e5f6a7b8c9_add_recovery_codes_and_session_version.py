"""add recovery codes, ip lockouts, and user session/forgot-lockout columns

Revision ID: d4e5f6a7b8c9
Revises: b7e2b1a4c9d3
Create Date: 2026-10-11 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'b7e2b1a4c9d3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('failed_forgot_attempts', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('forgot_locked_until', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('session_version', sa.Integer(), nullable=False, server_default='0'))

    op.create_table(
        'recovery_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('code_hash', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('recovery_codes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_recovery_codes_user_id'), ['user_id'], unique=False)

    op.create_table(
        'ip_lockouts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ip', sa.String(length=45), nullable=False),
        sa.Column('scope', sa.String(length=30), nullable=False),
        sa.Column('failed_attempts', sa.Integer(), nullable=False),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ip', 'scope', name='uq_ip_lockout_ip_scope'),
    )


def downgrade():
    op.drop_table('ip_lockouts')

    with op.batch_alter_table('recovery_codes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_recovery_codes_user_id'))
    op.drop_table('recovery_codes')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('session_version')
        batch_op.drop_column('forgot_locked_until')
        batch_op.drop_column('failed_forgot_attempts')
