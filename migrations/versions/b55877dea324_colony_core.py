"""colony core: habits.category, colonies, buildings

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

    op.create_table(
        'buildings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('colony_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.Column('slot', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finishes_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('damaged_on', sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(['colony_id'], ['colonies.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('colony_id', 'type', name='uq_building_colony_type'),
    )
    with op.batch_alter_table('buildings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_buildings_colony_id'), ['colony_id'], unique=False)


def downgrade():
    with op.batch_alter_table('buildings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_buildings_colony_id'))
    op.drop_table('buildings')

    with op.batch_alter_table('colonies', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_colonies_user_id'))
    op.drop_table('colonies')

    with op.batch_alter_table('habits', schema=None) as batch_op:
        batch_op.drop_column('category')
