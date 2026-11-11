"""Store each account's personal campaign progress and sync revision."""
from alembic import op
import sqlalchemy as sa

revision = '0007'
down_revision = '0006'


def upgrade():
    op.add_column(
        'users',
        sa.Column('solo_progress', sa.JSON(), nullable=False, server_default='{}'),
    )
    op.add_column(
        'users',
        sa.Column('solo_progress_revision', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade():
    op.drop_column('users', 'solo_progress_revision')
    op.drop_column('users', 'solo_progress')
