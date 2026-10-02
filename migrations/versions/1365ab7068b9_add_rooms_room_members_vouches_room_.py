"""add rooms, room_members, vouches, room_crowns, habits.room_id

Revision ID: 1365ab7068b9
Revises: 3d1d5917434d
Create Date: 2026-10-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1365ab7068b9'
down_revision = '3d1d5917434d'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('rooms',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=60), nullable=False),
    sa.Column('emoji', sa.String(length=8), nullable=False),
    sa.Column('creator_id', sa.Integer(), nullable=False),
    sa.Column('duration_days', sa.Integer(), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('invite_token', sa.String(length=64), nullable=False),
    sa.ForeignKeyConstraint(['creator_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('rooms', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_rooms_creator_id'), ['creator_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_rooms_invite_token'), ['invite_token'], unique=True)

    op.create_table('room_members',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('room_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('joined_on', sa.Date(), nullable=False),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('room_id', 'user_id', name='uq_room_member')
    )
    with op.batch_alter_table('room_members', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_room_members_room_id'), ['room_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_room_members_user_id'), ['user_id'], unique=False)

    op.create_table('vouches',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('checkin_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('emoji', sa.String(length=8), nullable=False),
    sa.ForeignKeyConstraint(['checkin_id'], ['checkins.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('checkin_id', 'user_id', name='uq_vouch_checkin_user')
    )
    with op.batch_alter_table('vouches', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_vouches_checkin_id'), ['checkin_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_vouches_user_id'), ['user_id'], unique=False)

    op.create_table('room_crowns',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('room_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('checkin_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['checkin_id'], ['checkins.id'], ),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('room_id', 'date', name='uq_room_crown_room_date')
    )
    with op.batch_alter_table('room_crowns', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_room_crowns_checkin_id'), ['checkin_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_room_crowns_room_id'), ['room_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_room_crowns_user_id'), ['user_id'], unique=False)

    with op.batch_alter_table('habits', schema=None) as batch_op:
        batch_op.add_column(sa.Column('room_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_habits_room_id'), ['room_id'], unique=False)
        batch_op.create_foreign_key('fk_habits_room_id_rooms', 'rooms', ['room_id'], ['id'])


def downgrade():
    with op.batch_alter_table('habits', schema=None) as batch_op:
        batch_op.drop_constraint('fk_habits_room_id_rooms', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_habits_room_id'))
        batch_op.drop_column('room_id')

    with op.batch_alter_table('room_crowns', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_room_crowns_user_id'))
        batch_op.drop_index(batch_op.f('ix_room_crowns_room_id'))
        batch_op.drop_index(batch_op.f('ix_room_crowns_checkin_id'))
    op.drop_table('room_crowns')

    with op.batch_alter_table('vouches', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_vouches_user_id'))
        batch_op.drop_index(batch_op.f('ix_vouches_checkin_id'))
    op.drop_table('vouches')

    with op.batch_alter_table('room_members', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_room_members_user_id'))
        batch_op.drop_index(batch_op.f('ix_room_members_room_id'))
    op.drop_table('room_members')

    with op.batch_alter_table('rooms', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_rooms_invite_token'))
        batch_op.drop_index(batch_op.f('ix_rooms_creator_id'))
    op.drop_table('rooms')
