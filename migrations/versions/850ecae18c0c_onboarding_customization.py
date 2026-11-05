"""onboarding customization: users.avatar, colonies.look

users.avatar stays NULL until the user finishes (or skips) the
commander step - that NULL is the one and only "has this user
onboarded yet" sentinel for the whole feature (see habitual.avatar).
colonies.look gets a real starter default instead, so there's never a
second independent "not done yet" state to keep in sync with the
first - a brand-new Colony row is never "mid-onboarding" with respect
to its look, only the user's avatar can be.

Revision ID: 850ecae18c0c
Revises: b55877dea324
Create Date: 2026-11-05 17:22:27.112368

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '850ecae18c0c'
down_revision = 'b55877dea324'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('avatar', sa.JSON(), nullable=True))

    with op.batch_alter_table('colonies', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'look', sa.JSON(), nullable=False,
            server_default=sa.text('\'{"world": "rust", "atmosphere": "steel", "ring": "none", "moons": "none"}\''),
        ))


def downgrade():
    with op.batch_alter_table('colonies', schema=None) as batch_op:
        batch_op.drop_column('look')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('avatar')
