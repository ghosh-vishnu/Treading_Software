from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.trade import Trade
from app.models.user import User


class RiskService:
    def validate_trade(self, db: Session, user: User, symbol: str, quantity: Decimal, price: Decimal) -> None:
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")
        if not user.trading_enabled:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Trading is disabled for this user")

        now = datetime.utcnow()
        start_of_day = datetime(now.year, now.month, now.day)
        daily_trades = db.query(Trade).filter(Trade.user_id == user.id, Trade.created_at >= start_of_day).count()
        if daily_trades >= user.max_trades_per_day:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Maximum trades per day exceeded")

        daily_pnl = db.query(Trade).filter(Trade.user_id == user.id, Trade.created_at >= start_of_day).all()
        realized_pnl = sum(Decimal(str(trade.pnl)) for trade in daily_pnl)
        if realized_pnl <= -abs(Decimal(user.max_daily_loss)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Daily loss limit reached")

        if quantity <= 0 or price <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid trade parameters")


risk_service = RiskService()