import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Integer, BigInteger, JSON, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    login: Mapped[str] = mapped_column(String(32), unique=True)
    nickname: Mapped[str] = mapped_column(String(40))
    password_hash: Mapped[str] = mapped_column(String(256))
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    player_profiles: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Server(Base):
    __tablename__ = 'servers'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Instance(Base):
    __tablename__ = 'instances'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    server_id: Mapped[str] = mapped_column(ForeignKey('servers.id'), index=True)
    address: Mapped[str] = mapped_column(String(64))
    port: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Wallet(Base):
    __tablename__ = 'wallets'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    tickets: Mapped[int] = mapped_column(BigInteger, default=0)
    purple_tickets: Mapped[int] = mapped_column(BigInteger, default=0)
    gold_pass_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Ownership(Base):
    __tablename__ = 'ownerships'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Order(Base):
    __tablename__ = 'orders'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    request_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GlobalProfile(Base):
    __tablename__ = 'global_profiles'
    __table_args__ = (UniqueConstraint('user_id', 'profile_name'),)
    normalized_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    profile_name: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Match(Base):
    __tablename__ = 'matches'
    instance_id: Mapped[str] = mapped_column(ForeignKey('instances.id'), primary_key=True)
    match_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    report_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LeagueStats(Base):
    __tablename__ = 'league_stats'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    season: Mapped[str] = mapped_column(String(7), primary_key=True)
    points: Mapped[int] = mapped_column(Integer, default=0)
    games: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)


class Tournament(Base):
    __tablename__ = 'tournaments'
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    game: Mapped[str] = mapped_column(String(100))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    definition: Mapped[dict] = mapped_column(JSON, default=dict)


class TournamentEntry(Base):
    __tablename__ = 'tournament_entries'
    __table_args__ = (UniqueConstraint('user_id', 'request_id'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tournament_id: Mapped[str] = mapped_column(ForeignKey('tournaments.id'), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    request_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RewardChest(Base):
    __tablename__ = 'reward_chests'
    __table_args__ = (UniqueConstraint('user_id', 'slot'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    appearance: Mapped[str] = mapped_column(String(8))
    slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contents: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    unlock_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RewardMessage(Base):
    __tablename__ = 'reward_messages'
    __table_args__ = (UniqueConstraint('user_id', 'source'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    source: Mapped[str] = mapped_column(String(150))
    tournament_id: Mapped[str | None] = mapped_column(ForeignKey('tournaments.id'), nullable=True)
    chest_id: Mapped[str] = mapped_column(ForeignKey('reward_chests.id'))
    kind: Mapped[str] = mapped_column(String(24))
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
