from alembic import context
from sqlalchemy import create_engine
from community_backend.config import Settings
from community_backend.models import Base

config = Settings()
with create_engine(config.database_url).connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
