from datetime import datetime

from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str | None] = mapped_column(String(100), unique=True, index=True, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    age: Mapped[int | None] = mapped_column(nullable=True)
    experience_level: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bio: Mapped[str | None] = mapped_column(String(500), nullable=True)
    public_profile: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    trading_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    max_daily_loss: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("500"), nullable=False)
    max_trades_per_day: Mapped[int] = mapped_column(default=50, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    trades = relationship("Trade", back_populates="user", cascade="all,delete-orphan")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all,delete-orphan")
    strategies = relationship("Strategy", back_populates="user", cascade="all,delete-orphan")
    signals = relationship("Signal", back_populates="user", cascade="all,delete-orphan")
    broker_accounts = relationship("BrokerAccount", back_populates="user", cascade="all,delete-orphan")
    followers = relationship(
        "CopyRelationship",
        foreign_keys="CopyRelationship.leader_id",
        back_populates="leader",
        cascade="all,delete-orphan",
    )
    leaders = relationship(
        "CopyRelationship",
        foreign_keys="CopyRelationship.follower_id",
        back_populates="follower",
        cascade="all,delete-orphan",
    )
