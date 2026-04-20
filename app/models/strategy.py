from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    strategy_tag: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    is_public: Mapped[bool] = mapped_column(default=False, nullable=False)
    exchange: Mapped[str] = mapped_column(String(80), default="Delta Exchange", nullable=False)
    risk_level: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    followers: Mapped[int] = mapped_column(default=0, nullable=False)
    recommended_margin: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("1000"), nullable=False)
    mdd_percent: Mapped[Decimal] = mapped_column(Numeric(7, 2), default=Decimal("0"), nullable=False)
    win_rate_percent: Mapped[Decimal] = mapped_column(Numeric(7, 2), default=Decimal("0"), nullable=False)
    pnl: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"), nullable=False)
    roi_percent: Mapped[Decimal] = mapped_column(Numeric(7, 2), default=Decimal("0"), nullable=False)
    chart_points: Mapped[str | None] = mapped_column(Text, nullable=True)
    academy_slugs: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="strategies")
    signals = relationship("Signal", back_populates="strategy", cascade="all,delete-orphan")