"""account deletion support: delete-attempt lockout, nullable room_crowns.user_id

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-10-12 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'f2a3b4c5d6e7'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('failed_delete_attempts', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('delete_locked_until', sa.DateTime(timezone=True), nullable=True))

    # Lets a finalized crown survive the winner deleting their whole
    # account (not just leaving the room) - same idea as checkin_id
    # already being nullable for the "left the room" case.
    with op.batch_alter_table('room_crowns', schema=None) as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.Integer(), nullable=True)


def downgrade():
    with op.batch_alter_table('room_crowns', schema=None) as batch_op:
        batch_op.alter_column('user_id', existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('delete_locked_until')
        batch_op.drop_column('failed_delete_attempts')
