from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(4), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    order_type: Mapped[str] = mapped_column(String(20), default="MARKET", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    pnl: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"), nullable=False)
    broker_order_id: Mapped[str] = mapped_column(String(100), nullable=False)
    broker: Mapped[str] = mapped_column(String(50), default="delta", nullable=False)
    strategy_tag: Mapped[str | None] = mapped_column(String(100), nullable=True)
    leader_trade_id: Mapped[int | None] = mapped_column(ForeignKey("trades.id"), nullable=True)
    stop_loss: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    take_profit: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="trades")
    leader_trade = relationship("Trade", remote_side=[id])
