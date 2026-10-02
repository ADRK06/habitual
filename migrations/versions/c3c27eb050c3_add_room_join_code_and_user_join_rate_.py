"""add room.join_code and user join-code rate-limit columns

Revision ID: c3c27eb050c3
Revises: 1365ab7068b9
Create Date: 2026-10-02 00:00:00.000000

"""
import secrets

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'c3c27eb050c3'
down_revision = '1365ab7068b9'
branch_labels = None
depends_on = None

# Self-contained on purpose (not imported from habitual.rooms) - a migration
# must keep working even if the application's own constant later changes.
_JOIN_CODE_ALPHABET = "".join(
    c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" if c not in "0O1IL"
)


def upgrade():
    with op.batch_alter_table('rooms', schema=None) as batch_op:
        batch_op.add_column(sa.Column('join_code', sa.String(length=6), nullable=True))

    # Backfill every existing room with a unique code before the column can
    # be made NOT NULL + UNIQUE below.
    rooms_table = sa.table('rooms', sa.column('id', sa.Integer), sa.column('join_code', sa.String))
    conn = op.get_bind()
    used_codes = set()
    for row in conn.execute(sa.select(rooms_table.c.id)):
        while True:
            code = "".join(secrets.choice(_JOIN_CODE_ALPHABET) for _ in range(6))
            if code not in used_codes:
                used_codes.add(code)
                break
        conn.execute(rooms_table.update().where(rooms_table.c.id == row.id).values(join_code=code))

    with op.batch_alter_table('rooms', schema=None) as batch_op:
        batch_op.alter_column('join_code', existing_type=sa.String(length=6), nullable=False)
        batch_op.create_index(batch_op.f('ix_rooms_join_code'), ['join_code'], unique=True)

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('failed_join_attempts', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('join_locked_until', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('join_locked_until')
        batch_op.drop_column('failed_join_attempts')

    with op.batch_alter_table('rooms', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_rooms_join_code'))
        batch_op.drop_column('join_code')
