from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.signal import Signal
from app.models.strategy import Strategy
from app.models.user import User
from app.repositories.signal_repository import SignalRepository
from app.repositories.strategy_repository import StrategyRepository
from app.schemas.strategy import StrategyCreateRequest, StrategySignalRequest, StrategySignalResponse, StrategyResponse
from app.services.market_data_service import market_data_service
from app.services.trade_service import trade_service


class StrategyService:
    def create_strategy(self, db: Session, user: User, payload: StrategyCreateRequest) -> StrategyResponse:
        repo = StrategyRepository(db)
        existing = repo.get_by_tag(payload.strategy_tag)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Strategy tag already exists")

        strategy = Strategy(
            name=payload.name,
            description=payload.description,
            user_id=user.id,
            strategy_tag=payload.strategy_tag,
            is_public=payload.is_public,
        )
        repo.create(strategy)
        db.commit()
        db.refresh(strategy)
        return StrategyResponse.model_validate(strategy)

    def process_signal(self, db: Session, user: User, payload: StrategySignalRequest) -> StrategySignalResponse:
        strategy_repo = StrategyRepository(db)
        signal_repo = SignalRepository(db)
        strategy = strategy_repo.get_by_tag(payload.strategy_tag)
        if strategy is None:
            strategy = Strategy(
                name=payload.strategy_tag,
                description="Auto-created strategy from incoming signal",
                user_id=user.id,
                strategy_tag=payload.strategy_tag,
                is_public=False,
            )
            strategy_repo.create(strategy)
            db.flush()

        signal = Signal(
            strategy_id=strategy.id,
            user_id=user.id,
            symbol=payload.symbol,
            side=payload.side,
            confidence=Decimal(str(payload.confidence)),
            strategy_tag=payload.strategy_tag,
        )
        signal_repo.create(signal)
        db.commit()

        quantity = payload.quantity or Decimal("1")
        price = payload.price or market_data_service.get_latest_price(payload.symbol)
        if payload.confidence >= 0.6:
            from app.schemas.trade import TradeCreateRequest

            trade_request = TradeCreateRequest(
                symbol=payload.symbol,
                side=payload.side,  # type: ignore[arg-type]
                quantity=quantity,
                price=price,
                order_type=payload.order_type,  # type: ignore[arg-type]
                broker=payload.broker,  # type: ignore[arg-type]
                strategy_tag=payload.strategy_tag,
            )
            trade_service.execute_trade(db, user, trade_request)

        message = f"Signal stored for {payload.symbol} at confidence {payload.confidence:.2f}."
        return StrategySignalResponse(accepted=True, message=message)


strategy_service = StrategyService()
