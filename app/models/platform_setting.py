from datetime import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlatformSetting(Base):
    __tablename__ = "platform_settings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    site_name: Mapped[str] = mapped_column(String(120), default="Algo Trading Platform", nullable=False)
    support_email: Mapped[str] = mapped_column(String(255), default="support@example.com", nullable=False)
    fee_percent: Mapped[float] = mapped_column(default=0.1, nullable=False)
    profit_share_percent: Mapped[float] = mapped_column(default=20.0, nullable=False)
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    telegram_alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    exchange_api_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    exchange_api_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
