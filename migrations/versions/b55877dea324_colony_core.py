"""colony core: habits.category, rooms.category, colonies

No buildings table - a building's level is derived on read from
check-in counts (habitual.game.level_for_checkins), not stored. A
buildings table returns in a later phase when storm damage needs real
per-building state.

Revision ID: b55877dea324
Revises: 4137cd629e82
Create Date: 2026-11-05 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'b55877dea324'
down_revision = '4137cd629e82'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('habits', schema=None) as batch_op:
        batch_op.add_column(sa.Column('category', sa.String(length=20), nullable=False, server_default='other'))

    with op.batch_alter_table('rooms', schema=None) as batch_op:
        batch_op.add_column(sa.Column('category', sa.String(length=20), nullable=False, server_default='other'))

    op.create_table(
        'colonies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('planet_type', sa.String(length=20), nullable=False, server_default='rust'),
        sa.Column('created_on', sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('colonies', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_colonies_user_id'), ['user_id'], unique=True)


def downgrade():
    with op.batch_alter_table('colonies', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_colonies_user_id'))
    op.drop_table('colonies')

    with op.batch_alter_table('rooms', schema=None) as batch_op:
        batch_op.drop_column('category')

    with op.batch_alter_table('habits', schema=None) as batch_op:
        batch_op.drop_column('category')
