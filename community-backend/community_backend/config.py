from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='COMMUNITY_', env_file='.env')
    database_url: str = 'postgresql+psycopg://community:community@127.0.0.1:55432/community_dev'
    redis_url: str = 'redis://127.0.0.1:56379/0'
    # Required even in development; never ship a universal ticket signing key.
    secret: str = Field(min_length=43)
    access_seconds: int = Field(default=900, ge=1)
    refresh_seconds: int = Field(default=2592000, ge=1)
    lease_seconds: int = Field(default=30, ge=3, le=30)
    join_seconds: int = Field(default=30, ge=1, le=60)
    prepare_seconds: float = Field(default=5, gt=0, le=5)
    # Controlled servers only. Restrict further at the firewall in production.
    allowed_server_networks: str = '127.0.0.0/8,::1/128'
    test_purchases_enabled: bool = False
    profile_upgrade_tickets: int = Field(default=100, ge=0)
    tournament_period_seconds: int = Field(default=21600, ge=60, le=86400)

    @field_validator('secret')
    @classmethod
    def require_real_secret(cls, value):
        if value.startswith('REPLACE_'):
            raise ValueError('Replace COMMUNITY_SECRET with a generated random secret')
        return value
