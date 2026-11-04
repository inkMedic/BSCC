"""Initial community account and server registry."""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None


def upgrade():
    op.create_table('users',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('login', sa.String(32), nullable=False, unique=True),
        sa.Column('nickname', sa.String(40), nullable=False),
        sa.Column('password_hash', sa.String(256), nullable=False),
        sa.Column('disabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('servers',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(80), nullable=False),
        sa.Column('key_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('revoked', sa.Boolean(), nullable=False))
    op.create_table('instances',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('server_id', sa.String(36), sa.ForeignKey('servers.id'), nullable=False),
        sa.Column('address', sa.String(64), nullable=False),
        sa.Column('port', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_instances_server_id', 'instances', ['server_id'])


def downgrade():
    op.drop_table('instances')
    op.drop_table('servers')
    op.drop_table('users')
