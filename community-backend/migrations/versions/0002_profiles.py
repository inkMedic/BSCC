"""Community account profiles, independent of official account services."""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'


def upgrade():
    op.add_column('users', sa.Column('player_profiles', sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade():
    op.drop_column('users', 'player_profiles')
