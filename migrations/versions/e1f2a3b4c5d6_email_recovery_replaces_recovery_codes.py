"""email-based password recovery replaces recovery codes

Revision ID: e1f2a3b4c5d6
Revises: d4e5f6a7b8c9
Create Date: 2026-10-11 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'e1f2a3b4c5d6'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    # Recovery codes are gone - replaced by emailed verify/reset links.
    with op.batch_alter_table('recovery_codes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_recovery_codes_user_id'))
    op.drop_table('recovery_codes')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('pending_email', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=False)

    # Uniqueness only among VERIFIED emails - an unverified claim is
    # provisional (see habitual.auth._claim_verified_email), so two
    # accounts can share an unverified `email` until one of them actually
    # proves ownership. Plain op.create_index (not batch mode): Postgres
    # supports a partial index as a direct CREATE INDEX, no table rebuild.
    op.create_index(
        'uq_users_email_verified', 'users', ['email'], unique=True,
        postgresql_where=sa.text('email_verified_at IS NOT NULL'),
    )

    op.create_table(
        'email_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('purpose', sa.String(length=20), nullable=False),
        sa.Column('target_email', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('email_tokens', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_email_tokens_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_email_tokens_token_hash'), ['token_hash'], unique=True)

    # IpLockout -> RateLimit: it now also holds email-keyed (not just IP-
    # keyed) rate limits for forgot-password/resend-verification, so `ip`
    # becomes the more general `key` (and widens from 45 chars, enough for
    # an IPv6 address, to 255, enough for an email address).
    op.rename_table('ip_lockouts', 'rate_limits')
    with op.batch_alter_table('rate_limits', schema=None) as batch_op:
        batch_op.drop_constraint('uq_ip_lockout_ip_scope', type_='unique')
        batch_op.alter_column(
            'ip', new_column_name='key',
            existing_type=sa.String(length=45), type_=sa.String(length=255),
        )
        batch_op.alter_column('failed_attempts', new_column_name='attempts', existing_type=sa.Integer())
        batch_op.create_unique_constraint('uq_rate_limit_key_scope', ['key', 'scope'])


def downgrade():
    op.rename_table('rate_limits', 'ip_lockouts')
    with op.batch_alter_table('ip_lockouts', schema=None) as batch_op:
        batch_op.drop_constraint('uq_rate_limit_key_scope', type_='unique')
        batch_op.alter_column('attempts', new_column_name='failed_attempts', existing_type=sa.Integer())
        batch_op.alter_column(
            'key', new_column_name='ip',
            existing_type=sa.String(length=255), type_=sa.String(length=45),
        )
        batch_op.create_unique_constraint('uq_ip_lockout_ip_scope', ['ip', 'scope'])

    with op.batch_alter_table('email_tokens', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_email_tokens_token_hash'))
        batch_op.drop_index(batch_op.f('ix_email_tokens_user_id'))
    op.drop_table('email_tokens')

    op.drop_index('uq_users_email_verified', table_name='users')
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_email'))
        batch_op.drop_column('email_verified_at')
        batch_op.drop_column('pending_email')
        batch_op.drop_column('email')

    op.create_table(
        'recovery_codes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('code_hash', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('recovery_codes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_recovery_codes_user_id'), ['user_id'], unique=False)
