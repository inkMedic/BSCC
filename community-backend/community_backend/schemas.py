from typing import Literal, Any
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, ConfigDict


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Login(Strict):
    login: str = Field(pattern=r'^[a-zA-Z0-9_]{3,32}$')
    password: str = Field(min_length=10, max_length=128)

    @field_validator('login')
    @classmethod
    def normalize(cls, value):
        return value.lower()


class Register(Login):
    nickname: str = Field(min_length=1, max_length=40)


class Refresh(Strict):
    refresh_token: str = Field(min_length=40, max_length=100)


class PlayerProfile(Strict):
    character: str = Field(min_length=1, max_length=64)
    color: tuple[float, float, float]
    highlight: tuple[float, float, float]
    icon: str = Field(default='', max_length=32)
    global_: bool = Field(default=False, alias='global')

    @field_validator('color', 'highlight')
    @classmethod
    def valid_color(cls, value):
        import math
        if any(not math.isfinite(v) or not 0 <= v <= 10 for v in value):
            raise ValueError('Invalid color')
        return value


class Compatibility(Strict):
    engine_build: int = 23079
    scene_protocol: int = 57
    community_protocol: Literal[1] = 1
    assets: str = Field(default='23079', min_length=1, max_length=128)


class Purchase(Strict):
    request_id: UUID
    item_id: str = Field(min_length=1, max_length=100)
    currency: Literal['tokens', 'tickets', 'gold_pass', 'test']
    expected_price: int = Field(ge=0, le=1000000)


class UpgradeProfile(Strict):
    request_id: UUID
    name: str = Field(min_length=1, max_length=64)
    expected_price: int = Field(ge=0, le=1000000)


class MatchPlayer(Strict):
    uid: UUID
    placement: int = Field(ge=1, le=32)


class MatchReport(Strict):
    instance_id: UUID
    match_id: UUID
    started_at: float = Field(gt=0)
    ended_at: float = Field(gt=0)
    players: list[MatchPlayer] = Field(min_length=2, max_length=32)


class TournamentQuery(Strict):
    tournament_ids: list[str] | None = Field(default=None, max_length=20)
    num_scores: int = Field(default=1, ge=0, le=50)


class TournamentEnter(Strict):
    request_id: UUID


class TournamentScore(Strict):
    entry_id: UUID
    game: str = Field(min_length=1, max_length=100)
    score: int = Field(strict=True, ge=0, le=10000000)
    score_type: Literal['points', 'time'] = 'points'


class ChestOpen(Strict):
    request_id: UUID
    expected_price: int = Field(strict=True, ge=0, le=1000000)


class ServerRegister(Compatibility):
    server_id: UUID
    instance_id: UUID
    address: str
    port: int = Field(ge=1, le=65535)


class Join(Compatibility):
    instance_id: UUID
    join_attempt_id: UUID


class PartyState(Strict):
    name: str = Field(min_length=1, max_length=80)
    players: int = Field(ge=0, le=256)
    devices: int = Field(ge=0, le=256)
    device_capacity: int = Field(default=256, ge=1, le=256)
    capacity: int = Field(ge=1, le=256)
    public: bool
    ready: bool


class Control(Strict):
    version: Literal[1]
    message_id: UUID
    type: Literal['hello', 'heartbeat', 'party_state', 'join_prepared', 'join_rejected']
    server_id: UUID
    instance_id: UUID
    control_session_id: UUID
    payload: dict[str, Any] = Field(default_factory=dict)
