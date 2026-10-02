"""add badges table

Revision ID: f1a2b3c4d5e6
Revises: c3c27eb050c3
Create Date: 2026-10-02 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = 'c3c27eb050c3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'badges',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=30), nullable=False),
        sa.Column('earned_on', sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'type', name='uq_badge_user_type'),
    )
    with op.batch_alter_table('badges', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_badges_user_id'), ['user_id'], unique=False)


def downgrade():
    with op.batch_alter_table('badges', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_badges_user_id'))
    op.drop_table('badges')
