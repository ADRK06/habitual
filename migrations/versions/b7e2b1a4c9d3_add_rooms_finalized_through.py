"""add rooms.finalized_through for lazy crown finalization

Revision ID: b7e2b1a4c9d3
Revises: a9c1d2e3f4b5
Create Date: 2026-10-06 00:00:00.000000

NULL is safe for every existing room: finalize_due_crowns() treats it
exactly like "nothing finalized yet" (the same as before this column
existed), so the first finalize call after this migration just walks that
room's history once - bounded by its 7-90 day duration_days cap - then
never re-walks it again. No data backfill needed.
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'b7e2b1a4c9d3'
down_revision = 'a9c1d2e3f4b5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('rooms', schema=None) as batch_op:
        batch_op.add_column(sa.Column('finalized_through', sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table('rooms', schema=None) as batch_op:
        batch_op.drop_column('finalized_through')
