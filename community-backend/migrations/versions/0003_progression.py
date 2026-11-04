"""Community wallets, orders, global profiles, ranked match audit and seasons."""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'


def upgrade():
    op.create_table('wallets', sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('tokens', sa.BigInteger(), nullable=False, server_default='0'), sa.Column('tickets', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('gold_pass_until', sa.DateTime(timezone=True)),
        sa.CheckConstraint('tokens >= 0 AND tickets >= 0', name='wallet_nonnegative'))
    op.create_table('ownerships', sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('item_id', sa.String(100), primary_key=True), sa.Column('acquired_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('orders', sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('request_id', sa.String(36), primary_key=True), sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=False), sa.Column('result', sa.JSON(), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('global_profiles', sa.Column('normalized_name', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False), sa.Column('profile_name', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint('user_id', 'profile_name'))
    op.create_index('ix_global_profiles_user_id', 'global_profiles', ['user_id'])
    op.create_table('matches', sa.Column('instance_id', sa.String(36), sa.ForeignKey('instances.id'), primary_key=True),
        sa.Column('match_id', sa.String(36), primary_key=True), sa.Column('report_hash', sa.String(64), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('league_stats', sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), primary_key=True),
        sa.Column('season', sa.String(7), primary_key=True), sa.Column('points', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('games', sa.Integer(), nullable=False, server_default='0'), sa.Column('wins', sa.Integer(), nullable=False, server_default='0'))


def downgrade():
    for table in ['league_stats', 'matches', 'global_profiles', 'orders', 'ownerships', 'wallets']:
        op.drop_table(table)
