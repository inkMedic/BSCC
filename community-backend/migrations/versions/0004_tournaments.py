"""Community co-op tournaments, entries and reported scores."""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'


def upgrade():
    op.create_table('tournaments', sa.Column('id', sa.String(80), primary_key=True),
        sa.Column('game', sa.String(100), nullable=False), sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('tournament_entries', sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('tournament_id', sa.String(80), sa.ForeignKey('tournaments.id'), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('request_id', sa.String(36), nullable=False), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('score', sa.Integer()), sa.Column('score_hash', sa.String(64)), sa.Column('result', sa.JSON()),
        sa.Column('submitted_at', sa.DateTime(timezone=True)), sa.UniqueConstraint('user_id', 'request_id'),
        sa.CheckConstraint('score IS NULL OR (score >= 0 AND score <= 10000000)', name='tournament_score_bounds'))
    op.create_index('ix_tournament_entries_tournament_id', 'tournament_entries', ['tournament_id'])
    op.create_index('ix_tournament_entries_user_id', 'tournament_entries', ['user_id'])


def downgrade():
    op.drop_table('tournament_entries')
    op.drop_table('tournaments')
