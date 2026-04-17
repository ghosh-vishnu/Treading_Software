from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.signal import Signal
from app.models.strategy import Strategy
from app.models.user import User
from app.repositories.signal_repository import SignalRepository
from app.repositories.strategy_repository import StrategyRepository
from app.schemas.strategy import (
    AdminStrategyCreateRequest,
    AdminStrategyUpdateRequest,
    StrategyCreateRequest,
    StrategySignalRequest,
    StrategySignalResponse,
    StrategyResponse,
)
from app.services.market_data_service import market_data_service
from app.services.trade_service import trade_service


class StrategyService:
    @staticmethod
    def _encode_decimal_series(points: Iterable[Decimal]) -> str | None:
        normalized = [str(item.quantize(Decimal("0.01"))) for item in points]
        if not normalized:
            return None
        return ",".join(normalized)

    @staticmethod
    def _encode_slug_list(slugs: Iterable[str]) -> str | None:
        normalized = [item.strip() for item in slugs if item.strip()]
        if not normalized:
            return None
        return ",".join(normalized)

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
            chart_points=self._encode_decimal_series([]),
            academy_slugs=self._encode_slug_list([]),
        )
        repo.create(strategy)
        db.commit()
        db.refresh(strategy)
        return StrategyResponse.model_validate(strategy)

    def create_admin_strategy(self, db: Session, user: User, payload: AdminStrategyCreateRequest) -> StrategyResponse:
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
            exchange=payload.exchange,
            followers=payload.followers,
            recommended_margin=payload.recommended_margin,
            mdd_percent=payload.mdd_percent,
            win_rate_percent=payload.win_rate_percent,
            pnl=payload.pnl,
            roi_percent=payload.roi_percent,
            chart_points=self._encode_decimal_series(payload.chart_points),
            academy_slugs=self._encode_slug_list(payload.academy_slugs),
            is_featured=payload.is_featured,
        )

        repo.create(strategy)
        db.commit()
        db.refresh(strategy)
        return StrategyResponse.model_validate(strategy)

    def update_admin_strategy(
        self,
        db: Session,
        strategy_id: int,
        payload: AdminStrategyUpdateRequest,
    ) -> StrategyResponse:
        repo = StrategyRepository(db)
        strategy = repo.get_by_id(strategy_id)
        if not strategy:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

        updates = payload.model_dump(exclude_unset=True)
        new_tag = updates.get("strategy_tag")
        if new_tag and new_tag != strategy.strategy_tag:
            existing = repo.get_by_tag(new_tag)
            if existing:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Strategy tag already exists")

        for field_name, value in updates.items():
            if field_name == "chart_points" and value is not None:
                setattr(strategy, "chart_points", self._encode_decimal_series(value))
            elif field_name == "academy_slugs" and value is not None:
                setattr(strategy, "academy_slugs", self._encode_slug_list(value))
            else:
                setattr(strategy, field_name, value)

        db.add(strategy)
        db.commit()
        db.refresh(strategy)
        return StrategyResponse.model_validate(strategy)

    def delete_admin_strategy(self, db: Session, strategy_id: int) -> None:
        repo = StrategyRepository(db)
        strategy = repo.get_by_id(strategy_id)
        if not strategy:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Strategy not found")

        db.delete(strategy)
        db.commit()

    def list_public_strategies(self, db: Session) -> list[StrategyResponse]:
        repo = StrategyRepository(db)
        items = repo.list_public()
        return [StrategyResponse.model_validate(item) for item in items]

    def list_all_strategies(self, db: Session) -> list[StrategyResponse]:
        repo = StrategyRepository(db)
        items = repo.list_all()
        return [StrategyResponse.model_validate(item) for item in items]

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
