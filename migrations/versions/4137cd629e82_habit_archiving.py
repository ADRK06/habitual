"""habit archiving: habits.archived_at, first_day_points_suppressed,
room_id ON DELETE SET NULL

Revision ID: 4137cd629e82
Revises: f2a3b4c5d6e7
Create Date: 2026-11-04 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '4137cd629e82'
down_revision = 'f2a3b4c5d6e7'
branch_labels = None
depends_on = None


def _room_id_fk_name(bind):
    """Looks up the live name of the FK on habits.room_id instead of
    hard-coding it - dev and prod were both migrated through
    1365ab7068b9, which named it 'fk_habits_room_id_rooms', but nothing
    stops that from having drifted (a hand-fixed constraint, a restored
    dump, ...), so this reads whatever is actually there right now."""
    inspector = sa.inspect(bind)
    for fk in inspector.get_foreign_keys('habits'):
        if fk['constrained_columns'] == ['room_id']:
            return fk['name']
    raise RuntimeError("no FK found on habits.room_id - expected one from migration 1365ab7068b9")


def upgrade():
    with op.batch_alter_table('habits', schema=None) as batch_op:
        batch_op.add_column(sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column('first_day_points_suppressed', sa.Boolean(), nullable=False, server_default='false')
        )

    fk_name = _room_id_fk_name(op.get_bind())
    with op.batch_alter_table('habits', schema=None) as batch_op:
        batch_op.drop_constraint(fk_name, type_='foreignkey')
        batch_op.create_foreign_key(
            'fk_habits_room_id_rooms', 'rooms', ['room_id'], ['id'], ondelete='SET NULL'
        )


def downgrade():
    fk_name = _room_id_fk_name(op.get_bind())
    with op.batch_alter_table('habits', schema=None) as batch_op:
        batch_op.drop_constraint(fk_name, type_='foreignkey')
        batch_op.create_foreign_key('fk_habits_room_id_rooms', 'rooms', ['room_id'], ['id'])

    with op.batch_alter_table('habits', schema=None) as batch_op:
        batch_op.drop_column('first_day_points_suppressed')
        batch_op.drop_column('archived_at')
