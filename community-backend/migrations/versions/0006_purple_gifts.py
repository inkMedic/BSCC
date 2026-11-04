"""PurpleTickets balance and standalone administrative gift chests."""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'


def upgrade():
    op.add_column('wallets', sa.Column('purple_tickets', sa.BigInteger(), nullable=False, server_default='0'))
    op.create_check_constraint('wallet_purple_nonnegative', 'wallets', 'purple_tickets >= 0')
    op.alter_column('reward_messages', 'tournament_id', existing_type=sa.String(80), nullable=True)


def downgrade():
    # Administrative gifts cannot be represented by the older non-null schema.
    if op.get_bind().execute(sa.text('SELECT 1 FROM reward_messages WHERE tournament_id IS NULL LIMIT 1')).scalar_one_or_none():
        raise RuntimeError('Standalone gift records must be archived before downgrade')
    if op.get_bind().execute(sa.text('SELECT 1 FROM wallets WHERE purple_tickets <> 0 LIMIT 1')).scalar_one_or_none():
        raise RuntimeError('Nonzero purple balances cannot be dropped')
    op.alter_column('reward_messages', 'tournament_id', existing_type=sa.String(80), nullable=False)
    op.drop_constraint('wallet_purple_nonnegative', 'wallets', type_='check')
    op.drop_column('wallets', 'purple_tickets')
