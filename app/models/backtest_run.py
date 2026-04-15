from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    strategy_tag: Mapped[str] = mapped_column(String(120), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(20), default="1h", nullable=False)
    periods: Mapped[int] = mapped_column(default=200, nullable=False)
    roi: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    drawdown: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    win_rate: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    report_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
