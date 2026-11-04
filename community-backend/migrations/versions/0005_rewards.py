"""Persistent chest dock, queued prizes and tournament reward definitions."""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'


def upgrade():
    op.add_column('tournaments', sa.Column('definition', sa.JSON(), nullable=False, server_default='{}'))
    events = sa.table('tournaments', sa.column('id', sa.String), sa.column('definition', sa.JSON))
    op.execute(events.update().where(events.c.id.op('~')(r'^\d{4}-\d{2}-\d{2}-(runaround|last-stand)$')).values(
        definition=dict(rewards=True, score_type='points', lower=False, min_players=1, max_players=4)))
    op.create_table('reward_chests', sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('appearance', sa.String(8), nullable=False), sa.Column('slot', sa.Integer()),
        sa.Column('contents', sa.JSON(), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('unlock_at', sa.DateTime(timezone=True)), sa.Column('opened_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('user_id', 'slot'), sa.CheckConstraint('slot IS NULL OR (slot >= 0 AND slot <= 3)', name='chest_slot_bounds'))
    op.create_index('ix_reward_chests_user_id', 'reward_chests', ['user_id'])
    op.create_table('reward_messages', sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('source', sa.String(150), nullable=False), sa.Column('tournament_id', sa.String(80), sa.ForeignKey('tournaments.id'), nullable=False),
        sa.Column('chest_id', sa.String(36), sa.ForeignKey('reward_chests.id'), nullable=False),
        sa.Column('kind', sa.String(24), nullable=False), sa.Column('rank', sa.Integer()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False), sa.Column('claimed_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('user_id', 'source'))
    op.create_index('ix_reward_messages_user_id', 'reward_messages', ['user_id'])


def downgrade():
    op.drop_table('reward_messages')
    op.drop_table('reward_chests')
    op.drop_column('tournaments', 'definition')
