"""add habit frequency columns to habits and rooms

Revision ID: a9c1d2e3f4b5
Revises: f1a2b3c4d5e6
Create Date: 2026-10-02 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'a9c1d2e3f4b5'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('habits', schema=None) as batch_op:
        batch_op.add_column(sa.Column('frequency_type', sa.String(length=10), nullable=False, server_default='daily'))
        batch_op.add_column(sa.Column('frequency_days', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('frequency_target', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('frequency_changed_on', sa.Date(), nullable=True))

    with op.batch_alter_table('rooms', schema=None) as batch_op:
        batch_op.add_column(sa.Column('frequency_type', sa.String(length=10), nullable=False, server_default='daily'))
        batch_op.add_column(sa.Column('frequency_days', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('frequency_target', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('rooms', schema=None) as batch_op:
        batch_op.drop_column('frequency_target')
        batch_op.drop_column('frequency_days')
        batch_op.drop_column('frequency_type')

    with op.batch_alter_table('habits', schema=None) as batch_op:
        batch_op.drop_column('frequency_changed_on')
        batch_op.drop_column('frequency_target')
        batch_op.drop_column('frequency_days')
        batch_op.drop_column('frequency_type')
