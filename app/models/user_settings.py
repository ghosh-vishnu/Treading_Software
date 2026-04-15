from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True, nullable=False)
    theme: Mapped[str] = mapped_column(String(20), default="dark", nullable=False)
    accent_color: Mapped[str] = mapped_column(String(20), default="lime", nullable=False)
    notify_trade_alerts: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_strategy_alerts: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_system_alerts: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    default_lot_size: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("1"), nullable=False)
    max_open_positions: Mapped[int] = mapped_column(default=5, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
